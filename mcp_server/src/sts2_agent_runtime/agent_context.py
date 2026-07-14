from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import GameStateSnapshot, utc_now_iso


class DeckCardSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str
    name: str | None = None
    upgraded: bool = False
    card_type: str | None = None
    count: int = Field(ge=1)


class DeckAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["deck-assessment.v1"] = "deck-assessment.v1"
    deck_signature: str
    deck_size: int = Field(ge=0)
    cards: list[DeckCardSummary] = Field(default_factory=list)
    card_type_counts: dict[str, int] = Field(default_factory=dict)
    curse_count: int = Field(ge=0)
    relic_ids: list[str] = Field(default_factory=list)
    potion_ids: list[str] = Field(default_factory=list)
    deck_tags: list[str] = Field(default_factory=list)

    def to_prompt_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class StrategicPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["strategic-plan.v1"] = "strategic-plan.v1"
    version: int = Field(default=1, ge=1)
    based_on_deck_signature: str = "unknown"
    goal_zh: str = "稳定推进并保留足够生命值。"
    risk_budget: Literal["low", "balanced", "high"] = "balanced"
    path_preferences: list[str] = Field(default_factory=list)
    acquisition_priorities: list[str] = Field(default_factory=list)
    avoid_conditions: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)

    def to_prompt_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class StrategicPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_zh: str | None = Field(default=None, max_length=240)
    risk_budget: Literal["low", "balanced", "high"] | None = None
    path_preferences: list[str] | None = Field(default=None, max_length=8)
    acquisition_priorities: list[str] | None = Field(default=None, max_length=8)
    avoid_conditions: list[str] | None = Field(default=None, max_length=8)


class ExperienceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    segment_id: str | None = None
    step_indices: list[int] = Field(default_factory=list, max_length=12)


class ExperienceScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str | None = None
    screens: list[str] = Field(default_factory=list)
    min_floor: int | None = Field(default=None, ge=0)
    max_floor: int | None = Field(default=None, ge=0)
    deck_tags_any: list[str] = Field(default_factory=list)


class ExperienceLesson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["experience-lesson.v1"] = "experience-lesson.v1"
    lesson_id: str
    kind: Literal["strategy_experience", "runtime_observation"] = "strategy_experience"
    status: Literal["provisional", "active", "rejected"] = "provisional"
    scope: ExperienceScope = Field(default_factory=ExperienceScope)
    recommendation_zh: str = Field(min_length=1, max_length=500)
    rationale_zh: str = Field(min_length=1, max_length=800)
    counterexamples_zh: list[str] = Field(default_factory=list, max_length=5)
    evidence: ExperienceEvidence
    confidence: float = Field(ge=0, le=1)
    created_at: str = Field(default_factory=utc_now_iso)

    def to_prompt_entry(self) -> dict[str, Any]:
        return {
            "lesson_id": self.lesson_id,
            "status": self.status,
            "scope": self.scope.model_dump(mode="json"),
            "recommendation_zh": self.recommendation_zh,
            "rationale_zh": self.rationale_zh,
            "counterexamples_zh": self.counterexamples_zh,
            "confidence": self.confidence,
            "evidence": self.evidence.model_dump(mode="json"),
            "notice_zh": "这是历史复盘经验，不是游戏事实；live state 与 legal actions 优先。",
        }


class ExperienceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["experience-context.v1"] = "experience-context.v1"
    lesson_ids: list[str] = Field(default_factory=list)
    lessons: list[dict[str, Any]] = Field(default_factory=list)


def build_deck_assessment(state: GameStateSnapshot) -> DeckAssessment:
    run = state.state.get("run") if isinstance(state.state.get("run"), dict) else {}
    raw_cards = [card for card in run.get("deck") or [] if isinstance(card, dict)]
    grouped: dict[tuple[str, bool, str | None, str | None], int] = {}
    type_counts: dict[str, int] = {}
    curse_count = 0

    for card in raw_cards:
        card_id = str(card.get("card_id") or card.get("id") or "UNKNOWN_CARD")
        upgraded = bool(card.get("upgraded", False))
        name = _optional_text(card.get("name"))
        card_type = _optional_text(card.get("card_type") or card.get("type"))
        key = (card_id, upgraded, name, card_type)
        grouped[key] = grouped.get(key, 0) + 1
        if card_type:
            type_counts[card_type] = type_counts.get(card_type, 0) + 1
        if card_type and card_type.upper() == "CURSE":
            curse_count += 1
        elif bool(card.get("is_curse", False)):
            curse_count += 1

    cards = [
        DeckCardSummary(card_id=card_id, upgraded=upgraded, name=name, card_type=card_type, count=count)
        for (card_id, upgraded, name, card_type), count in grouped.items()
    ]
    cards.sort(key=lambda card: (card.card_id, card.upgraded, card.card_type or "", card.name or ""))
    relic_ids = sorted(
        str(relic.get("relic_id") or relic.get("id"))
        for relic in run.get("relics") or []
        if isinstance(relic, dict) and (relic.get("relic_id") or relic.get("id"))
    )
    potion_ids = sorted(
        str(potion.get("potion_id") or potion.get("id"))
        for potion in run.get("potions") or []
        if isinstance(potion, dict) and potion.get("occupied", True) and (potion.get("potion_id") or potion.get("id"))
    )
    signature_payload = {
        "cards": [card.model_dump(mode="json") for card in cards],
        "relic_ids": relic_ids,
        "potion_ids": potion_ids,
    }
    signature = _short_hash(signature_payload)
    tags = sorted({f"type:{card_type.lower()}" for card_type in type_counts} | ({"has_curse"} if curse_count else set()))
    return DeckAssessment(
        deck_signature=signature,
        deck_size=len(raw_cards),
        cards=cards,
        card_type_counts=dict(sorted(type_counts.items())),
        curse_count=curse_count,
        relic_ids=relic_ids,
        potion_ids=potion_ids,
        deck_tags=tags,
    )


class RunContextStore:
    """Owns deterministic in-run facts and the narrowly editable strategic plan."""

    def __init__(self, experience_repository: Any | None = None) -> None:
        self.experience_repository = experience_repository
        self.deck_assessment: DeckAssessment | None = None
        self.strategic_plan: StrategicPlan | None = None
        self._last_snapshot_marker: str | None = None

    def observe(self, state: GameStateSnapshot) -> bool:
        assessment = build_deck_assessment(state)
        changed = self.deck_assessment is None or assessment.deck_signature != self.deck_assessment.deck_signature
        self.deck_assessment = assessment
        if self.strategic_plan is None:
            self.strategic_plan = StrategicPlan(based_on_deck_signature=assessment.deck_signature)
        self._last_snapshot_marker = _snapshot_marker(state, assessment.deck_signature)
        return changed

    def apply_strategy_update(self, payload: Any, state: GameStateSnapshot) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"applied": False, "reason": "strategy_update_absent"}
        self.observe(state)
        try:
            update = StrategicPlanUpdate.model_validate(payload)
        except Exception as exc:
            return {"applied": False, "reason": "strategy_update_invalid", "error": str(exc)}
        if not update.model_fields_set:
            return {"applied": False, "reason": "strategy_update_empty"}
        assert self.deck_assessment is not None
        assert self.strategic_plan is not None
        values = self.strategic_plan.model_dump()
        values.update(update.model_dump(exclude_none=True))
        values["version"] = self.strategic_plan.version + 1
        values["based_on_deck_signature"] = self.deck_assessment.deck_signature
        values["updated_at"] = utc_now_iso()
        self.strategic_plan = StrategicPlan.model_validate(values)
        return {"applied": True, "version": self.strategic_plan.version}

    def prompt_context(self, state: GameStateSnapshot, agent_name: str) -> dict[str, Any]:
        self.observe(state)
        assert self.deck_assessment is not None
        assert self.strategic_plan is not None
        experience = self._experience_context(state)
        return {
            "packet": "run_context.v1",
            "agent_name": agent_name,
            "deck_assessment": self.deck_assessment.to_prompt_dict(),
            "strategic_plan": self.strategic_plan.to_prompt_dict(),
            "historical_experience": experience.model_dump(mode="json"),
        }

    def decision_metadata(self, state: GameStateSnapshot, agent_name: str) -> dict[str, Any]:
        self.observe(state)
        assert self.deck_assessment is not None
        assert self.strategic_plan is not None
        experience = self._experience_context(state)
        return {
            "name": agent_name,
            "deck_signature": self.deck_assessment.deck_signature,
            "strategic_plan_version": self.strategic_plan.version,
            "experience_lesson_ids": experience.lesson_ids,
        }

    def snapshot(self, state: GameStateSnapshot) -> dict[str, Any]:
        self.observe(state)
        assert self.deck_assessment is not None
        assert self.strategic_plan is not None
        return {
            "schema_version": "run-context-snapshot.v1",
            "observed_at": utc_now_iso(),
            "run_id": state.run_id,
            "screen": state.screen,
            "floor": _floor(state),
            "snapshot_marker": self._last_snapshot_marker,
            "deck_assessment": self.deck_assessment.model_dump(mode="json"),
            "strategic_plan": self.strategic_plan.model_dump(mode="json"),
        }

    def _experience_context(self, state: GameStateSnapshot) -> ExperienceContext:
        if self.experience_repository is None:
            return ExperienceContext()
        assert self.deck_assessment is not None
        return self.experience_repository.retrieve(state, self.deck_assessment)


def _optional_text(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _short_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _snapshot_marker(state: GameStateSnapshot, deck_signature: str) -> str:
    return _short_hash({"run_id": state.run_id, "screen": state.screen, "turn": state.turn, "floor": _floor(state), "deck": deck_signature})


def _floor(state: GameStateSnapshot) -> int | None:
    run = state.state.get("run") if isinstance(state.state.get("run"), dict) else {}
    value = run.get("floor")
    return value if isinstance(value, int) else None
