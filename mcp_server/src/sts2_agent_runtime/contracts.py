from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "mvp0.v1"

DecisionType = Literal["action", "wait", "stop", "needs_human"]


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


@dataclass(slots=True)
class GameStateSnapshot:
    schema_version: str
    source: str
    observed_at: str
    run_id: str
    game_version: str
    mod_version: str
    screen: str
    session: dict[str, Any]
    turn: int | None
    available_actions: list[str]
    state: dict[str, Any]
    raw_state: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        raw_payload: dict[str, Any],
        *,
        source: str,
        health: dict[str, Any] | None = None,
        observed_at: str | None = None,
    ) -> "GameStateSnapshot":
        raw = _data(raw_payload)
        health_data = _data(health or {})
        agent_view = raw.get("agent_view")
        compact = agent_view if isinstance(agent_view, dict) else raw
        actions = compact.get("available_actions") or compact.get("actions") or raw.get("available_actions") or []
        normalized_actions = [str(action.get("name") if isinstance(action, dict) else action) for action in actions]

        return cls(
            schema_version=SCHEMA_VERSION,
            source=source,
            observed_at=observed_at or utc_now_iso(),
            run_id=str(raw.get("run_id") or compact.get("run_id") or "run_unknown"),
            game_version=str(health_data.get("game_version") or "unknown"),
            mod_version=str(health_data.get("mod_version") or "unknown"),
            screen=str(compact.get("screen") or raw.get("screen") or "UNKNOWN"),
            session=dict(compact.get("session") or raw.get("session") or {}),
            turn=raw.get("turn"),
            available_actions=normalized_actions,
            state=raw,
            raw_state=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(slots=True)
class AgentAction:
    action: str
    legal_action_id: str | None = None
    card_index: int | None = None
    target_index: int | None = None
    option_index: int | None = None
    potion_index: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    client_context: dict[str, Any] = field(default_factory=dict)

    def to_request(self) -> dict[str, Any]:
        option_index = self.option_index
        if self.action in {"use_potion", "discard_potion"} and option_index is None:
            option_index = self.potion_index

        return {
            "action": self.action,
            "card_index": self.card_index,
            "target_index": self.target_index,
            "option_index": option_index,
            "client_context": self.client_context or {"source": "agent-runtime"},
            **self.payload,
        }

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(slots=True)
class PolicyDecision:
    type: DecisionType
    action: AgentAction | None = None
    action_plan: list[AgentAction] = field(default_factory=list)
    reason: str = ""
    confidence: float | None = None
    used_knowledge: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def action_decision(
        cls,
        action: AgentAction,
        *,
        reason: str,
        confidence: float | None = None,
        used_knowledge: list[str] | None = None,
    ) -> "PolicyDecision":
        return cls("action", action=action, reason=reason, confidence=confidence, used_knowledge=used_knowledge or [])

    @classmethod
    def action_plan_decision(
        cls,
        actions: list[AgentAction],
        *,
        reason: str,
        confidence: float | None = None,
        used_knowledge: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "PolicyDecision":
        return cls(
            "action",
            action=actions[0] if actions else None,
            action_plan=actions,
            reason=reason,
            confidence=confidence,
            used_knowledge=used_knowledge or [],
            metadata=metadata or {},
        )

    @classmethod
    def wait(cls, reason: str) -> "PolicyDecision":
        return cls("wait", reason=reason)

    @classmethod
    def stop(cls, reason: str) -> "PolicyDecision":
        return cls("stop", reason=reason)

    @classmethod
    def needs_human(cls, reason: str) -> "PolicyDecision":
        return cls("needs_human", reason=reason)

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        if self.action is not None:
            data["action"] = self.action.to_dict()
        return data


@dataclass(slots=True)
class ActionResult:
    ok: bool
    action: str
    status: str
    stable: bool
    message: str
    state: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, action: str) -> "ActionResult":
        data = _data(payload)
        return cls(
            ok=bool(payload.get("ok", True)),
            action=str(data.get("action") or action),
            status=str(data.get("status") or ("completed" if payload.get("ok", True) else "error")),
            stable=bool(data.get("stable", False)),
            message=str(data.get("message") or ""),
            state=data.get("state") if isinstance(data.get("state"), dict) else None,
            error=payload.get("error") if isinstance(payload.get("error"), dict) else None,
            raw=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(slots=True)
class KnowledgeContext:
    schema_version: str = SCHEMA_VERSION
    run_id: str = "run_unknown"
    refs: list[str] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)
    monsters: list[dict[str, Any]] = field(default_factory=list)
    potions: list[dict[str, Any]] = field(default_factory=list)
    relics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(slots=True)
class StepRecord:
    schema_version: str
    run_id: str
    segment_id: str
    step_index: int
    observed_at: str
    screen_before: str
    state_hash_before: str
    state_hash_after: str | None
    state_summary: dict[str, Any]
    knowledge_refs: list[str]
    decision: dict[str, Any]
    action_request: dict[str, Any] | None
    action_result: dict[str, Any] | None
    error: dict[str, Any] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(slots=True)
class TrajectorySegment:
    schema_version: str
    segment_id: str
    run_id: str
    start_reason: str
    checkpoint_hash: str
    start_floor: int | None
    start_screen: str
    start_hp: int | None
    observed_at: str
    parent_segment_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(slots=True)
class RunSummary:
    schema_version: str
    run_id: str
    result: str
    floor_reached: int | None
    terminal_screen: str
    terminal_reason: str
    step_count: int
    error_count: int
    observed_at: str
    duration_seconds: float | None = None
    token_usage: dict[str, int] = field(default_factory=dict)
    segment_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)
