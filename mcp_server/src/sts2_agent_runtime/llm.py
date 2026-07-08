from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib import request

from .contracts import AgentAction, GameStateSnapshot, KnowledgeContext, PolicyDecision
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
    def __init__(self, *, model: str | None = None, api_base: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self.api_base = (api_base or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAICompatiblePolicy.")

    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        prompt = {
            "instruction": (
                "Return exactly one legal PolicyDecision JSON object. Do not call tools. "
                "If any useful available action exists, type must be action. Never return needs_human, stop, or wait during combat. "
                "Choose only from available_actions and only use indices present in state. "
                "For play_card, use combat.hand[].index and obey requires_target/valid_target_indices. "
                "For option actions, set option_index. For potion actions, set potion_index."
            ),
            "response_schema": {
                "type": "action|wait|stop|needs_human",
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
            "screen": state.screen,
            "available_actions": state.available_actions,
            "state": _compact_state(state.state),
            "knowledge_refs": knowledge.refs,
        }
        response = self._chat(prompt)
        parsed = _parse_json_object(response)
        action_payload = _extract_action_payload(parsed)
        if parsed.get("type") != "action" and action_payload is None:
            if _has_useful_action(state.available_actions):
                raise ValueError(f"LLM returned non-action decision while actions are available: {parsed.get('type')!r}")
            return PolicyDecision(type=parsed.get("type", "needs_human"), reason=parsed.get("reason", "LLM non-action decision."))
        if action_payload is None:
            raise ValueError("LLM action decision did not include an action payload.")
        action = AgentAction(
            action=str(action_payload.get("action")),
            card_index=action_payload.get("card_index"),
            target_index=action_payload.get("target_index"),
            option_index=action_payload.get("option_index"),
            potion_index=action_payload.get("potion_index"),
        )
        return PolicyDecision.action_decision(action, reason=str(parsed.get("reason") or "LLM decision."), confidence=parsed.get("confidence"))

    def _chat(self, prompt: dict[str, Any]) -> str:
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
        with request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
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


def _has_useful_action(actions: list[str]) -> bool:
    passive = {"save_and_quit", "discard_potion"}
    return any(action not in passive for action in actions)
