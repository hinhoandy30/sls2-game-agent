from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib import error as urlerror, request

from .action_spec import action_spec_prompt_options, parse_llm_action_payload, parse_llm_action_plan_payload
from .contracts import GameStateSnapshot, KnowledgeContext, PolicyDecision
from .legal_actions import action_from_legal_action_id, build_legal_actions
from .policies import Policy, ScreenRouter

DEFAULT_OPENAI_MODEL = "deepseek-v4-flash"
GAMEPLAY_LLM_SCREENS = {
    "MAP",
    "COMBAT",
    "REWARD",
    "CARD_SELECTION",
    "CHEST",
    "EVENT",
    "SHOP",
    "REST",
    "MODAL",
}


class OpenAICompatiblePolicy:
    def __init__(
        self,
        *,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        enable_action_plan: bool = False,
        max_plan_actions: int = 5,
        max_retries: int = 2,
        request_timeout_seconds: float = 60.0,
    ) -> None:
        self.model = model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self.api_base = (api_base or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.enable_action_plan = enable_action_plan
        self.max_plan_actions = max(1, min(max_plan_actions, 8))
        self.max_retries = max(0, max_retries)
        self.request_timeout_seconds = request_timeout_seconds
        self.last_call_metadata: dict[str, Any] = {}
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAICompatiblePolicy.")

    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        legal_actions = build_legal_actions(state)
        prompt = {
            "instruction": (
                "Return exactly one legal PolicyDecision JSON object. Do not call tools. "
                "If any useful available action exists, type must be action. Never return needs_human, stop, or wait during combat. "
                "Prefer selecting one id from legal_actions and return it as legal_action_id. "
                "Do not invent card_index, potion_index, option_index, or target_index when a legal_action_id is available."
            ),
            "response_schema": {
                "type": "action|wait|stop|needs_human",
                "legal_action_id": "string id from legal_actions|null",
                "action": {
                    "action": "string from available_actions",
                    "card_index": "integer|null",
                    "target_index": "integer|null",
                    "option_index": "integer|null",
                    "potion_index": "integer|null",
                },
                "reason": "short reason",
                "confidence": "number 0..1",
            },
            "planning_mode": "action_plan" if self.enable_action_plan and state.screen == "COMBAT" else "single_action",
            "action_plan_rules": (
                {
                    "enabled": True,
                    "max_actions": self.max_plan_actions,
                    "use_only_on_screen": "COMBAT",
                    "schema": {
                        "type": "action",
                        "action_plan": {
                            "actions": [
                                {
                                    "legal_action_id": "string id from legal_actions|null",
                                    "action": "string from available_actions",
                                    "card_index": "integer|null",
                                    "target_index": "integer|null",
                                    "option_index": "integer|null",
                                    "potion_index": "integer|null",
                                }
                            ],
                            "stop_conditions": ["screen_changes", "card_index_not_available", "new_selection_or_reward_opens"],
                        },
                        "reason": "short reason",
                        "confidence": "number 0..1",
                    },
                    "important": (
                        "When planning multiple combat actions, every plan item MUST use legal_action_id, never raw card_index or target_index. "
                        "The runtime will fresh-read and validate after every action, and stops the remaining plan when an entity disappears or the screen changes."
                    ),
                }
                if self.enable_action_plan and state.screen == "COMBAT"
                else {"enabled": False}
            ),
            "screen": state.screen,
            "available_actions": state.available_actions,
            "legal_actions": legal_actions,
            "available_action_options": action_spec_prompt_options(state),
            "state": _compact_state(state.state),
            "knowledge_refs": knowledge.refs,
        }
        response = self._chat(prompt)
        llm_metadata = dict(getattr(self, "last_call_metadata", {}) or {})
        parsed = self._parse_or_repair_json(response, prompt, llm_metadata)
        plan_payload = _extract_action_plan_payload(parsed)
        if self.enable_action_plan and state.screen == "COMBAT" and plan_payload is not None:
            actions, stop_conditions = parse_llm_action_plan_payload(
                plan_payload,
                state,
                require_legal_action_ids=True,
            )
            actions = actions[: self.max_plan_actions]
            decision = PolicyDecision.action_plan_decision(
                actions,
                reason=str(parsed.get("reason") or "LLM action plan."),
                confidence=parsed.get("confidence"),
                metadata={"stop_conditions": stop_conditions},
            )
            decision.metadata["llm"] = llm_metadata
            return decision
        legal_action_id = parsed.get("legal_action_id")
        if isinstance(legal_action_id, str) and legal_action_id:
            action = action_from_legal_action_id(legal_action_id, state)
            decision = PolicyDecision.action_decision(action, reason=str(parsed.get("reason") or "LLM legal action decision."), confidence=parsed.get("confidence"))
            decision.metadata["llm"] = llm_metadata
            return decision

        action_payload = _extract_action_payload(parsed)
        if parsed.get("type") != "action" and action_payload is None:
            if _has_useful_action(state.available_actions):
                raise ValueError(f"LLM returned non-action decision while actions are available: {parsed.get('type')!r}")
            return PolicyDecision(type=parsed.get("type", "needs_human"), reason=parsed.get("reason", "LLM non-action decision."))
        if action_payload is None:
            raise ValueError("LLM action decision did not include an action payload.")
        action = parse_llm_action_payload(action_payload, state)
        decision = PolicyDecision.action_decision(action, reason=str(parsed.get("reason") or "LLM decision."), confidence=parsed.get("confidence"))
        decision.metadata["llm"] = llm_metadata
        return decision

    def _parse_or_repair_json(self, response: str, original_prompt: dict[str, Any], aggregate_metadata: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        current_response = response
        for attempt in range(self.max_retries + 1):
            try:
                return _parse_json_object(current_response)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                repair_prompt = {
                    "instruction": "Repair the previous response into exactly one valid JSON object. Output JSON only.",
                    "original_decision_prompt": original_prompt,
                    "invalid_response": current_response[:12000],
                    "parse_error": str(exc),
                }
                current_response = self._chat(repair_prompt)
                _merge_llm_metadata(aggregate_metadata, getattr(self, "last_call_metadata", {}) or {})
        raise last_error or ValueError("Unable to parse LLM JSON response.")

    def _chat(self, prompt: dict[str, Any]) -> str:
        started_at = time.perf_counter()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an STS2 policy module. Output only JSON."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "temperature": 0.1,
        }
        req = request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with request.urlopen(req, timeout=self.request_timeout_seconds) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except (TimeoutError, urlerror.URLError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                time.sleep(0.5 * (attempt + 1))
        else:
            raise last_error or RuntimeError("LLM request failed.")

        self.last_call_metadata = {
            "provider": "openai-compatible",
            "model": str(data.get("model") or self.model),
            "duration_seconds": round(time.perf_counter() - started_at, 6),
            "usage": _normalize_usage(data.get("usage")),
        }
        return str(data["choices"][0]["message"]["content"])


class LLMScreenRouter:
    def __init__(
        self,
        *,
        llm_policy: Policy,
        base_router: ScreenRouter | None = None,
        llm_screens: set[str] | None = None,
    ) -> None:
        self.llm_policy = llm_policy
        self.base_router = base_router or ScreenRouter()
        self.llm_screens = llm_screens or GAMEPLAY_LLM_SCREENS

    def select(self, state: GameStateSnapshot) -> Policy:
        if state.screen in self.llm_screens:
            return self.llm_policy
        return self.base_router.select(state)


def _compact_state(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": raw.get("run_id"),
        "screen": raw.get("screen"),
        "session": raw.get("session"),
        "turn": raw.get("turn"),
        "character_select": raw.get("character_select"),
        "combat": raw.get("combat"),
        "run": raw.get("run"),
        "map": raw.get("map"),
        "reward": raw.get("reward"),
        "selection": raw.get("selection"),
        "event": raw.get("event"),
        "modal": raw.get("modal"),
        "shop": raw.get("shop"),
        "rest": raw.get("rest"),
        "chest": raw.get("chest"),
    }


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if match:
            parsed = json.loads(match.group(1))
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise
            parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object.")
    return parsed


def _extract_action_payload(parsed: dict[str, Any]) -> dict[str, Any] | None:
    action_payload = parsed.get("action")
    if isinstance(action_payload, str):
        return {
            "action": action_payload,
            "card_index": parsed.get("card_index"),
            "target_index": parsed.get("target_index"),
            "option_index": parsed.get("option_index"),
            "potion_index": parsed.get("potion_index"),
        }
    if isinstance(action_payload, dict) and action_payload.get("action"):
        return action_payload
    if isinstance(parsed.get("action_name"), str):
        return {
            "action": parsed["action_name"],
            "card_index": parsed.get("card_index"),
            "target_index": parsed.get("target_index"),
            "option_index": parsed.get("option_index"),
            "potion_index": parsed.get("potion_index"),
        }
    return None


def _extract_action_plan_payload(parsed: dict[str, Any]) -> dict[str, Any] | None:
    action_plan = parsed.get("action_plan")
    if isinstance(action_plan, dict) and isinstance(action_plan.get("actions"), list):
        return action_plan
    actions = parsed.get("actions")
    if isinstance(actions, list):
        return {
            "actions": actions,
            "stop_conditions": parsed.get("stop_conditions") or [],
        }
    return None


def _has_useful_action(actions: list[str]) -> bool:
    passive = {"save_and_quit", "discard_potion"}
    return any(action not in passive for action in actions)


def _normalize_usage(raw_usage: Any) -> dict[str, int]:
    if not isinstance(raw_usage, dict):
        return {}
    usage: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = raw_usage.get(key)
        if isinstance(value, int):
            usage[key] = value
    details = raw_usage.get("completion_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), int):
        usage["reasoning_tokens"] = details["reasoning_tokens"]
    cached = raw_usage.get("prompt_tokens_details")
    if isinstance(cached, dict) and isinstance(cached.get("cached_tokens"), int):
        usage["cached_tokens"] = cached["cached_tokens"]
    return usage


def _merge_llm_metadata(base: dict[str, Any], extra: dict[str, Any]) -> None:
    if not extra:
        return
    if extra.get("model"):
        base["model"] = extra["model"]
    if extra.get("provider"):
        base["provider"] = extra["provider"]
    if isinstance(extra.get("duration_seconds"), (int, float)):
        base["duration_seconds"] = round(float(base.get("duration_seconds") or 0) + float(extra["duration_seconds"]), 6)

    base_usage = base.setdefault("usage", {})
    extra_usage = extra.get("usage")
    if isinstance(base_usage, dict) and isinstance(extra_usage, dict):
        for key, value in extra_usage.items():
            if isinstance(value, int):
                base_usage[key] = int(base_usage.get(key, 0)) + value
