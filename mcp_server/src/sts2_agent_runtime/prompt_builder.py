from __future__ import annotations

import hashlib
import json
from typing import Any


PROMPT_LAYOUT_VERSION = "prompt-layout.v1"
SYSTEM_MESSAGE = (
    "You are an STS2 policy module. Output only JSON. "
    "Live game state is authoritative for legality and current values; "
    "knowledge is background reference only."
)


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sort_entries(entries: list[dict[str, Any]], *id_keys: str) -> list[dict[str, Any]]:
    def sort_key(entry: dict[str, Any]) -> tuple[str, str]:
        for key in id_keys:
            value = entry.get(key)
            if value is not None:
                return str(value), _canonical_json(entry)
        return "", _canonical_json(entry)

    return sorted(entries, key=sort_key)


def canonical_knowledge_packet(knowledge: dict[str, Any]) -> dict[str, Any]:
    """Normalize static lookup output so equivalent encounters share a prompt prefix."""
    return {
        "refs": sorted({str(item) for item in knowledge.get("refs", [])}),
        "cards": _sort_entries(list(knowledge.get("cards", [])), "card_id", "id"),
        "card_priorities": _sort_entries(list(knowledge.get("card_priorities", [])), "card_id", "strategy_id"),
        "monsters": _sort_entries(list(knowledge.get("monsters", [])), "enemy_id", "id"),
        "events": _sort_entries(list(knowledge.get("events", [])), "event_id", "id"),
        "potions": _sort_entries(list(knowledge.get("potions", [])), "potion_id", "id"),
        "relics": _sort_entries(list(knowledge.get("relics", [])), "relic_id", "id"),
    }


class PromptBuilder:
    """Build a cache-friendly, inspectable chat request for one policy decision."""

    def build_decision(
        self,
        *,
        system_message: str = SYSTEM_MESSAGE,
        instruction: str,
        response_schema: dict[str, Any],
        planning_mode: str,
        action_plan_rules: dict[str, Any],
        screen: str,
        available_actions: list[str],
        legal_actions: list[dict[str, Any]],
        plan_legal_actions: list[dict[str, Any]],
        available_action_options: list[dict[str, Any]],
        state: dict[str, Any],
        knowledge: dict[str, Any],
        agent_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        canonical_knowledge = canonical_knowledge_packet(knowledge)
        screen_contract = {
            "packet": "screen_contract.v1",
            "screen": screen,
            "instruction": instruction,
            "response_schema": response_schema,
            "planning_mode": planning_mode,
            "action_plan_rules": action_plan_rules,
        }
        knowledge_packet = {
            "packet": "knowledge_packet.v1",
            "knowledge": canonical_knowledge,
        }
        decision_state = {
            "packet": "decision_state.v1",
            "screen": screen,
            "available_actions": available_actions,
            "legal_actions": legal_actions,
            "plan_legal_actions": plan_legal_actions,
            "available_action_options": available_action_options,
            "state": state,
        }
        context_packet = {"packet": "run_context.v1", "context": agent_context} if agent_context else None
        contents = {
            "system": system_message,
            "screen_contract": _canonical_json(screen_contract),
            "knowledge_packet": _canonical_json(knowledge_packet),
            "decision_state": _canonical_json(decision_state),
        }
        if context_packet is not None:
            contents["run_context"] = _canonical_json(context_packet)
        message_characters = {name: len(content) for name, content in contents.items()}
        message_characters["total"] = sum(message_characters.values())
        knowledge_packet_hash = hashlib.sha256(contents["knowledge_packet"].encode("utf-8")).hexdigest()[:16]

        # The top-level fields make fake policies and local debugging straightforward.
        # Only ``messages`` are transmitted to the model provider.
        return {
            "instruction": instruction,
            "response_schema": response_schema,
            "planning_mode": planning_mode,
            "action_plan_rules": action_plan_rules,
            "screen": screen,
            "available_actions": available_actions,
            "legal_actions": legal_actions,
            "plan_legal_actions": plan_legal_actions,
            "available_action_options": available_action_options,
            "state": state,
            "knowledge": canonical_knowledge,
            "messages": [
                {"role": "system", "content": contents["system"]},
                {"role": "user", "content": contents["screen_contract"]},
                *([{ "role": "user", "content": contents["run_context"] }] if "run_context" in contents else []),
                {"role": "user", "content": contents["knowledge_packet"]},
                {"role": "user", "content": contents["decision_state"]},
            ],
            "prompt_metadata": {
                "layout_version": PROMPT_LAYOUT_VERSION,
                "knowledge_packet_hash": knowledge_packet_hash,
                "message_characters": message_characters,
            },
        }

    def build_repair(
        self,
        *,
        original_prompt: dict[str, Any],
        invalid_response: str,
        parse_error: str,
    ) -> dict[str, Any]:
        repair_packet = {
            "packet": "repair_response.v1",
            "instruction": "Repair the previous response into exactly one valid JSON object. Output JSON only.",
            "response_schema": original_prompt.get("response_schema"),
            "invalid_response": invalid_response[:12000],
            "parse_error": parse_error,
        }
        content = _canonical_json(repair_packet)
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": content},
            ],
            "prompt_metadata": {
                "layout_version": "prompt-repair.v1",
                "parent_knowledge_packet_hash": (original_prompt.get("prompt_metadata") or {}).get("knowledge_packet_hash"),
                "message_characters": {"system": len(SYSTEM_MESSAGE), "repair": len(content), "total": len(SYSTEM_MESSAGE) + len(content)},
            },
        }
