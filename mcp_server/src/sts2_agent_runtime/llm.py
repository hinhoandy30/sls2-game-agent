from __future__ import annotations

import json
import os
from typing import Any
from urllib import request

from .contracts import AgentAction, GameStateSnapshot, KnowledgeContext, PolicyDecision

DEFAULT_OPENAI_MODEL = "deepseek-v4-flash"


class OpenAICompatiblePolicy:
    def __init__(self, *, model: str | None = None, api_base: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self.api_base = (api_base or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAICompatiblePolicy.")

    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        prompt = {
            "instruction": "Return one legal PolicyDecision JSON. Prefer simple legal actions. Do not call tools.",
            "screen": state.screen,
            "available_actions": state.available_actions,
            "state": _compact_state(state.state),
            "knowledge_refs": knowledge.refs,
        }
        response = self._chat(prompt)
        parsed = json.loads(response)
        if parsed.get("type") != "action":
            return PolicyDecision(type=parsed.get("type", "needs_human"), reason=parsed.get("reason", "LLM non-action decision."))
        action_payload = parsed.get("action") or {}
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


def _compact_state(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": raw.get("run_id"),
        "screen": raw.get("screen"),
        "session": raw.get("session"),
        "turn": raw.get("turn"),
        "combat": raw.get("combat"),
        "run": raw.get("run"),
        "map": raw.get("map"),
        "reward": raw.get("reward"),
        "selection": raw.get("selection"),
        "modal": raw.get("modal"),
    }
