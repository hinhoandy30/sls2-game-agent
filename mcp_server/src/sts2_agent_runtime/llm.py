from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Literal
from urllib import error as urlerror, request

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError

from .action_spec import action_spec_prompt_options, parse_llm_action_payload, parse_llm_action_plan_payload
from .contracts import AgentAction, GameStateSnapshot, KnowledgeContext, PolicyDecision
from .legal_actions import action_from_legal_action_id, build_legal_actions
from .policies import Policy, ScreenRouter
from .prompt_builder import PromptBuilder
from .route_planning import build_route_planning_payload

DEFAULT_OPENAI_MODEL = "deepseek-v4-flash"
GAMEPLAY_LLM_SCREENS = {
    "MAP",
    "COMBAT",
    "REWARD",
    "CARD_SELECTION",
    "BUNDLE_SELECTION",
    "CHEST",
    "EVENT",
    "SHOP",
    "REST",
    "MODAL",
}


class CombatReplanBoundary(BaseModel):
    """The earliest action after which the current plan must be discarded."""

    model_config = ConfigDict(extra="forbid")

    legal_action_id: str = Field(min_length=1)
    reason: Literal[
        "draw_cards",
        "random_effect",
        "card_generation",
        "discard_or_exhaust",
        "entity_missing",
        "unknown_complex_effect",
    ]


class CombatAudit(BaseModel):
    """Short, inspectable conclusions instead of storing a long reasoning trace."""

    model_config = ConfigDict(extra="forbid")

    primary_target_id: str | None = None
    lethal_this_turn: Literal["yes", "no", "unknown"]
    defense_posture: Literal[
        "lethal",
        "full_block",
        "accept_damage_for_tempo",
        "unavoidable_damage",
        "unknown",
    ]
    risk_summary_zh: str = Field(min_length=1, max_length=360)
    replan_after: list[CombatReplanBoundary] = Field(default_factory=list, max_length=1)


class OpenAICompatiblePolicy:
    def __init__(
        self,
        *,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        enable_action_plan: bool = True,
        max_plan_actions: int = 5,
        max_retries: int = 2,
        request_timeout_seconds: float = 60.0,
        agent_name: str = "general",
        agent_instruction: str = "",
        context_provider: Callable[[GameStateSnapshot], dict[str, Any]] | None = None,
        metadata_provider: Callable[[GameStateSnapshot], dict[str, Any]] | None = None,
        strategy_update_handler: Callable[[Any, GameStateSnapshot], dict[str, Any]] | None = None,
    ) -> None:
        self.model = model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self.api_base = (api_base or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.enable_action_plan = enable_action_plan
        self.max_plan_actions = max(1, min(max_plan_actions, 8))
        self.max_retries = max(0, max_retries)
        self.request_timeout_seconds = request_timeout_seconds
        self.agent_name = agent_name
        self.agent_instruction = agent_instruction
        self.context_provider = context_provider
        self.metadata_provider = metadata_provider
        self.strategy_update_handler = strategy_update_handler
        self.prompt_builder = PromptBuilder()
        self.last_call_metadata: dict[str, Any] = {}
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAICompatiblePolicy.")

    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        legal_actions = build_legal_actions(state)
        stable_plan_enabled, plan_reason = _stable_combat_plan_gate(state, legal_actions, self.enable_action_plan)
        plan_legal_actions = _stable_plan_legal_actions(legal_actions) if stable_plan_enabled else []
        prompt_builder = getattr(self, "prompt_builder", None)
        if prompt_builder is None:
            # Test/evaluation policy subclasses may deliberately skip the networked base constructor.
            prompt_builder = PromptBuilder()
            self.prompt_builder = prompt_builder
        agent_name = getattr(self, "agent_name", "general")
        agent_instruction = getattr(self, "agent_instruction", "")
        context_provider = getattr(self, "context_provider", None)
        agent_context = context_provider(state) if callable(context_provider) else None
        instruction = _decision_instruction(stable_plan_enabled)
        if agent_instruction:
            instruction = f"{agent_instruction}\n\n{instruction}"
        requires_combat_audit = stable_plan_enabled and agent_name == "combat"
        response_schema = _response_schema(stable_plan_enabled, requires_combat_audit=requires_combat_audit)
        if callable(getattr(self, "strategy_update_handler", None)):
            response_schema = {**response_schema, "strategy_update": _strategy_update_schema()}
        prompt = prompt_builder.build_decision(
            system_message=_agent_system_message(agent_name),
            instruction=instruction,
            response_schema=response_schema,
            planning_mode="stable_action_plan" if stable_plan_enabled else "single_action",
            action_plan_rules=_action_plan_rules(stable_plan_enabled, self.max_plan_actions, plan_reason),
            screen=state.screen,
            available_actions=state.available_actions,
            legal_actions=plan_legal_actions if stable_plan_enabled else legal_actions,
            plan_legal_actions=plan_legal_actions,
            available_action_options=[] if stable_plan_enabled else action_spec_prompt_options(state),
            state=_compact_state(state.state, legal_actions=legal_actions),
            knowledge=_knowledge_prompt_payload(knowledge),
            agent_context=agent_context,
        )
        response = self._chat(prompt)
        llm_metadata = dict(getattr(self, "last_call_metadata", {}) or {})
        parsed = self._parse_or_repair_json(response, prompt, llm_metadata)
        agent_metadata = self._agent_metadata(state, agent_name)
        strategy_update_handler = getattr(self, "strategy_update_handler", None)
        if callable(strategy_update_handler):
            agent_metadata["strategy_update"] = strategy_update_handler(parsed.get("strategy_update"), state)
        plan_payload = _extract_action_plan_payload(parsed)
        if stable_plan_enabled and plan_payload is not None:
            allowed_plan_ids = {str(action["id"]) for action in plan_legal_actions}
            try:
                actions, stop_conditions = parse_llm_action_plan_payload(
                    plan_payload,
                    state,
                    require_legal_action_ids=True,
                    allowed_legal_action_ids=allowed_plan_ids,
                )
                combat_audit = _parse_combat_audit(parsed, actions) if requires_combat_audit else None
            except ValueError as exc:
                parsed = self._repair_invalid_action_plan(
                    original_prompt=prompt,
                    invalid_response=parsed,
                    validation_error=str(exc),
                    allowed_plan_ids=allowed_plan_ids,
                    aggregate_metadata=llm_metadata,
                )
                repaired_plan = _extract_action_plan_payload(parsed)
                if repaired_plan is None:
                    raise ValueError("LLM repair did not return an action_plan.")
                actions, stop_conditions = parse_llm_action_plan_payload(
                    repaired_plan,
                    state,
                    require_legal_action_ids=True,
                    allowed_legal_action_ids=allowed_plan_ids,
                )
                combat_audit = _parse_combat_audit(parsed, actions) if requires_combat_audit else None
            actions = actions[: self.max_plan_actions]
            decision = PolicyDecision.action_plan_decision(
                actions,
                reason=str(parsed.get("reason") or "LLM action plan."),
                confidence=parsed.get("confidence"),
                metadata={
                    "stop_conditions": stop_conditions,
                    "planning": {"mode": "stable_action_plan", "gate_reason": plan_reason},
                },
            )
            decision.metadata["llm"] = llm_metadata
            if combat_audit is not None:
                decision.metadata["combat_audit"] = combat_audit.model_dump(mode="json")
            self._attach_agent_metadata(decision, agent_metadata)
            return decision
        legal_action_id = parsed.get("legal_action_id")
        if isinstance(legal_action_id, str) and legal_action_id:
            action = action_from_legal_action_id(legal_action_id, state)
            decision = PolicyDecision.action_decision(action, reason=str(parsed.get("reason") or "LLM legal action decision."), confidence=parsed.get("confidence"))
            decision.metadata["planning"] = {
                "mode": "single_action",
                "gate_reason": plan_reason,
                "fallback_from_stable_plan": self.enable_action_plan and state.screen == "COMBAT",
            }
            decision.metadata["llm"] = llm_metadata
            self._attach_agent_metadata(decision, agent_metadata)
            return decision

        action_payload = _extract_action_payload(parsed)
        if parsed.get("type") != "action" and action_payload is None:
            if _has_useful_action(state.available_actions):
                raise ValueError(f"LLM returned non-action decision while actions are available: {parsed.get('type')!r}")
            decision = PolicyDecision(type=parsed.get("type", "needs_human"), reason=parsed.get("reason", "LLM non-action decision."))
            decision.metadata["llm"] = llm_metadata
            self._attach_agent_metadata(decision, agent_metadata)
            return decision
        if action_payload is None:
            raise ValueError("LLM action decision did not include an action payload.")
        action = parse_llm_action_payload(action_payload, state)
        decision = PolicyDecision.action_decision(action, reason=str(parsed.get("reason") or "LLM decision."), confidence=parsed.get("confidence"))
        decision.metadata["planning"] = {
            "mode": "single_action",
            "gate_reason": plan_reason,
            "fallback_from_stable_plan": self.enable_action_plan and state.screen == "COMBAT",
        }
        decision.metadata["llm"] = llm_metadata
        self._attach_agent_metadata(decision, agent_metadata)
        return decision

    def _agent_metadata(self, state: GameStateSnapshot, agent_name: str) -> dict[str, Any]:
        metadata_provider = getattr(self, "metadata_provider", None)
        metadata = metadata_provider(state) if callable(metadata_provider) else {"name": agent_name}
        if not isinstance(metadata, dict):
            metadata = {"name": agent_name}
        metadata.setdefault("name", agent_name)
        return metadata

    @staticmethod
    def _attach_agent_metadata(decision: PolicyDecision, metadata: dict[str, Any]) -> None:
        decision.metadata["agent"] = metadata
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
                repair_prompt = self.prompt_builder.build_repair(
                    original_prompt=original_prompt,
                    invalid_response=current_response,
                    parse_error=str(exc),
                )
                current_response = self._chat(repair_prompt)
                _merge_llm_metadata(aggregate_metadata, getattr(self, "last_call_metadata", {}) or {})
        raise last_error or ValueError("Unable to parse LLM JSON response.")

    def _repair_invalid_action_plan(
        self,
        *,
        original_prompt: dict[str, Any],
        invalid_response: dict[str, Any],
        validation_error: str,
        allowed_plan_ids: set[str],
        aggregate_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        packet = {
            "packet": "repair_action_plan.v1",
            "instruction": "Return exactly one corrected JSON decision. action_plan.actions must contain one or more legal_action_id values from allowed_plan_legal_action_ids.",
            "response_schema": original_prompt.get("response_schema"),
            "invalid_decision": invalid_response,
            "validation_error": validation_error,
            "allowed_plan_legal_action_ids": sorted(allowed_plan_ids),
        }
        content = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        repair_prompt = {
            "messages": [
                {"role": "system", "content": _agent_system_message(str(getattr(self, "agent_name", "combat")))},
                {"role": "user", "content": content},
            ],
            "prompt_metadata": {
                "layout_version": "action-plan-repair.v1",
                "message_characters": {"repair": len(content)},
            },
        }
        response = self._chat(repair_prompt)
        _merge_llm_metadata(aggregate_metadata, getattr(self, "last_call_metadata", {}) or {})
        return self._parse_or_repair_json(response, repair_prompt, aggregate_metadata)

    def _chat(self, prompt: dict[str, Any]) -> str:
        started_at = time.perf_counter()
        messages = prompt.get("messages")
        if not isinstance(messages, list):
            messages = [
                {"role": "system", "content": "You are an STS2 policy module. Output only JSON."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ]
        payload = {
            "model": self.model,
            "messages": messages,
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
            except urlerror.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"LLM HTTP {exc.code}: {body[:1000]}") from exc
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
            **dict(prompt.get("prompt_metadata") or {}),
        }
        return str(data["choices"][0]["message"]["content"])


def _knowledge_prompt_payload(knowledge: KnowledgeContext) -> dict[str, Any]:
    to_prompt_dict = getattr(knowledge, "to_prompt_dict", None)
    if callable(to_prompt_dict):
        return to_prompt_dict()

    return {
        "refs": list(getattr(knowledge, "refs", []) or []),
        "cards": list(getattr(knowledge, "cards", []) or []),
        "card_priorities": list(getattr(knowledge, "card_priorities", []) or []),
        "monsters": list(getattr(knowledge, "monsters", []) or []),
        "events": list(getattr(knowledge, "events", []) or []),
        "potions": list(getattr(knowledge, "potions", []) or []),
        "relics": list(getattr(knowledge, "relics", []) or []),
    }


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


def _stable_combat_plan_gate(
    state: GameStateSnapshot,
    legal_actions: list[dict[str, Any]],
    enabled: bool,
) -> tuple[bool, str]:
    if not enabled:
        return False, "disabled_by_configuration"
    if state.screen != "COMBAT":
        return False, "not_combat"

    card_actions = [item for item in legal_actions if item.get("action") == "play_card"]
    for action in card_actions:
        if not isinstance(action.get("card_instance_id"), str):
            return False, "card_instance_id_missing"
        if action.get("target_index") is not None and not isinstance(action.get("target_instance_id"), str):
            return False, "target_instance_id_missing"
    potion_actions = [item for item in legal_actions if item.get("action") == "use_potion"]
    for action in potion_actions:
        if action.get("target_index") is not None and not isinstance(action.get("target_instance_id"), str):
            return False, "potion_target_instance_id_missing"
    return True, "stable_combat_identity_available"


def _stable_plan_legal_actions(legal_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combat plans may play stable cards, use usable potions, and end the turn."""
    return [
        action
        for action in legal_actions
        if action.get("action") in {"play_card", "use_potion", "end_turn"}
    ]


def _decision_instruction(stable_plan_enabled: bool) -> str:
    if stable_plan_enabled:
        return (
            "Return exactly one legal combat PolicyDecision JSON object. Do not call tools. "
            "Plan this combat action window once: choose an ordered sequence of up to the allowed number of actions, then let the runtime execute it. "
            "Every action_plan item MUST contain exactly one legal_action_id from plan_legal_actions. "
            "card_index and target_index are old snapshot-relative positions: never output them, never reason with them, and never adjust them with arithmetic. "
            "The legal_action_id identifies the specific card and enemy instance. Include only actions that are sensible from the current hand and energy; include end_turn when appropriate and only as the final item. "
            "The runtime re-reads state after every action and will stop/replan if a card, target, or screen changes."
        )
    return (
        "Return exactly one legal PolicyDecision JSON object. Do not call tools. "
        "If any useful available action exists, type must be action. Never return needs_human, stop, or wait during combat. "
        "Prefer selecting one id from legal_actions and return it as legal_action_id. "
        "Do not invent card_index, potion_index, option_index, or target_index when a legal_action_id is available."
    )


def _response_schema(stable_plan_enabled: bool, *, requires_combat_audit: bool = False) -> dict[str, Any]:
    if stable_plan_enabled:
        schema = {
            "type": "action",
            "action_plan": {
                "actions": [{"legal_action_id": "required string id from plan_legal_actions"}],
                "stop_conditions": ["entity_missing", "screen_changed", "new_selection"],
            },
            "reason": "short reason",
            "confidence": "number 0..1",
        }
        if requires_combat_audit:
            schema["combat_audit"] = {
                "primary_target_id": "enemy_instance_id|null",
                "lethal_this_turn": "yes|no|unknown",
                "defense_posture": "lethal|full_block|accept_damage_for_tempo|unavoidable_damage|unknown",
                "risk_summary_zh": "short Chinese factual summary",
                "replan_after": [
                    {
                        "legal_action_id": "the earliest planned boundary action id",
                        "reason": "draw_cards|random_effect|card_generation|discard_or_exhaust|entity_missing|unknown_complex_effect",
                    }
                ],
            }
        return schema
    return {
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
    }


def _strategy_update_schema() -> dict[str, Any]:
    return {
        "goal_zh": "optional short strategic goal",
        "risk_budget": "optional low|balanced|high",
        "path_preferences": ["optional short preferences"],
        "acquisition_priorities": ["optional short priorities"],
        "avoid_conditions": ["optional short avoidance conditions"],
    }


def _agent_system_message(agent_name: str) -> str:
    return (
        f"You are the STS2 {agent_name} policy module. Output only JSON. "
        "You must not call tools or control the game directly. "
        "Live game state is authoritative for legality and current values; "
        "curated knowledge and historical experience are background reference only."
    )


def _parse_combat_audit(payload: dict[str, Any], actions: list[AgentAction]) -> CombatAudit:
    try:
        audit = CombatAudit.model_validate(payload.get("combat_audit"))
    except PydanticValidationError as exc:
        raise ValueError(f"Invalid combat_audit: {exc}") from exc

    planned_ids = {action.legal_action_id for action in actions if action.legal_action_id}
    for boundary in audit.replan_after:
        if boundary.legal_action_id not in planned_ids:
            raise ValueError("combat_audit.replan_after must reference a legal_action_id in action_plan.")
        if actions[-1].legal_action_id != boundary.legal_action_id:
            raise ValueError("A combat action plan must end at its declared replan boundary.")
    return audit


def _action_plan_rules(stable_plan_enabled: bool, max_actions: int, reason: str) -> dict[str, Any]:
    if not stable_plan_enabled:
        return {"enabled": False, "reason": reason}
    return {
        "enabled": True,
        "max_actions": max_actions,
        "use_only_on_screen": "COMBAT",
        "plan_item_schema": {"legal_action_id": "required string id from plan_legal_actions"},
        "important": (
            "Use the stable legal_action_id only. Do not include action, card_index, target_index, option_index, or potion_index in action_plan items. "
            "A plan is valid only while its referenced entities still exist in fresh state."
        ),
    }


def _compact_state(raw: dict[str, Any], *, legal_actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    agent_view = raw.get("agent_view") if isinstance(raw.get("agent_view"), dict) else {}
    agent_run = agent_view.get("run") if isinstance(agent_view.get("run"), dict) else {}
    compact = {
        "run_id": raw.get("run_id"),
        "screen": raw.get("screen"),
        "session": raw.get("session"),
        "turn": raw.get("turn"),
        "character_select": raw.get("character_select"),
        "combat": raw.get("combat"),
        "run": raw.get("run"),
        "map": _compact_map(raw.get("map")) if raw.get("screen") == "MAP" else raw.get("map"),
        "reward": raw.get("reward"),
        "selection": raw.get("selection"),
        "bundles": raw.get("bundles"),
        "event": raw.get("event"),
        "modal": raw.get("modal"),
        "shop": raw.get("shop"),
        "rest": raw.get("rest"),
        "chest": raw.get("chest"),
        "combat_piles": agent_run.get("piles"),
    }
    route_planning = (
        build_route_planning_payload(raw, legal_actions or [], include_route_candidates=False)
        if raw.get("screen") == "MAP"
        else None
    )
    if route_planning is not None:
        compact["route_planning"] = route_planning
    return compact


def _compact_map(map_payload: Any) -> Any:
    if not isinstance(map_payload, dict):
        return map_payload
    return {
        "current_node": map_payload.get("current_node"),
        "starting_node": map_payload.get("starting_node"),
        "boss_node": map_payload.get("boss_node"),
        "second_boss_node": map_payload.get("second_boss_node"),
        "rows": map_payload.get("rows"),
        "cols": map_payload.get("cols"),
        "is_travel_enabled": map_payload.get("is_travel_enabled"),
        "is_traveling": map_payload.get("is_traveling"),
        "map_generation_count": map_payload.get("map_generation_count"),
        "available_nodes": map_payload.get("available_nodes"),
        "local_vote": map_payload.get("local_vote"),
        "player_votes": map_payload.get("player_votes"),
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
