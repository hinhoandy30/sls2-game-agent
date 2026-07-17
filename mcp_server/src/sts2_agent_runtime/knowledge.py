from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import GameStateSnapshot, KnowledgeContext


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    title_zh: str
    url: str
    retrieved_at: str


class MonsterMoveKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_zh: str
    effect_zh: str


class MonsterKnowledgeFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sts2-monster-knowledge.v1"]
    kind: Literal["monster"]
    enemy_id: str
    name_zh: str
    act_ids: list[str] = Field(min_length=1)
    encounter_pool_zh: str
    summary_zh: str
    pattern_zh: str
    moves: list[MonsterMoveKnowledge] = Field(min_length=1)
    risk_facts_zh: list[str]
    sources: list[KnowledgeSource] = Field(min_length=1)

    def to_prompt_entry(self) -> dict[str, Any]:
        return {
            "enemy_id": self.enemy_id,
            "name_zh": self.name_zh,
            "summary_zh": self.summary_zh,
            "pattern_zh": self.pattern_zh,
            "moves": [move.model_dump() for move in self.moves],
            "risk_facts_zh": self.risk_facts_zh,
            "source_refs": [source.ref for source in self.sources],
        }


class EventKnowledgeFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sts2-event-knowledge.v1"]
    kind: Literal["event"]
    event_id: str
    name_zh: str
    act_ids: list[str] = Field(min_length=1)
    summary_zh: str
    flow_facts_zh: list[str]
    sources: list[KnowledgeSource] = Field(min_length=1)

    def to_prompt_entry(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "name_zh": self.name_zh,
            "summary_zh": self.summary_zh,
            "flow_facts_zh": self.flow_facts_zh,
            "source_refs": [source.ref for source in self.sources],
        }


class CardUpgradeKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_zh: str
    changes_zh: list[str]


class CardKnowledgeFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sts2-card-knowledge.v1"]
    kind: Literal["card"]
    card_id: str
    name_zh: str
    character_ids: list[str] = Field(min_length=1)
    card_type: str
    rarity: str
    cost_zh: str
    summary_zh: str
    mechanics_zh: list[str]
    tags: list[str]
    upgrade: CardUpgradeKnowledge | None = None
    sources: list[KnowledgeSource] = Field(min_length=1)

    def to_prompt_entry(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "name_zh": self.name_zh,
            "card_type": self.card_type,
            "rarity": self.rarity,
            "cost_zh": self.cost_zh,
            "summary_zh": self.summary_zh,
            "mechanics_zh": self.mechanics_zh,
            "tags": self.tags,
            "upgrade": self.upgrade.model_dump() if self.upgrade is not None else None,
            "source_refs": [source.ref for source in self.sources],
        }


class CardPriorityKnowledgeFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sts2-card-priority-strategy.v1"]
    kind: Literal["card_priority"]
    strategy_id: str
    card_id: str
    name_zh: str
    character_ids: list[str] = Field(min_length=1)
    baseline_priority: Literal["very_high", "high", "medium", "low", "avoid", "unknown"]
    role_tags: list[str]
    good_when_zh: list[str]
    bad_when_zh: list[str]
    pick_vs_skip_zh: list[str]
    upgrade_priority_zh: str
    notes_zh: list[str]
    sources: list[KnowledgeSource] = Field(min_length=1)

    def to_prompt_entry(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "card_id": self.card_id,
            "name_zh": self.name_zh,
            "baseline_priority": self.baseline_priority,
            "role_tags": self.role_tags,
            "good_when_zh": self.good_when_zh,
            "bad_when_zh": self.bad_when_zh,
            "pick_vs_skip_zh": self.pick_vs_skip_zh,
            "upgrade_priority_zh": self.upgrade_priority_zh,
            "notes_zh": self.notes_zh,
            "source_refs": [source.ref for source in self.sources],
        }


class KnowledgeProvider:
    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or Path(__file__).resolve().parents[2] / "data" / "knowledge" / "v1"
        self._monster_cache: dict[str, MonsterKnowledgeFile | None] = {}
        self._event_cache: dict[str, EventKnowledgeFile | None] = {}
        self._card_cache: dict[str, CardKnowledgeFile | None] = {}
        self._card_priority_cache: dict[str, CardPriorityKnowledgeFile | None] = {}

    def for_state(self, state: GameStateSnapshot) -> KnowledgeContext:
        raw = state.state
        refs: list[str] = []
        cards: list[dict[str, Any]] = []
        card_priorities: list[dict[str, Any]] = []
        monsters: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []

        combat = raw.get("combat") if isinstance(raw.get("combat"), dict) else {}
        for enemy in combat.get("enemies") or []:
            enemy_id = enemy.get("enemy_id") or enemy.get("id")
            if enemy_id:
                normalized_id = str(enemy_id)
                refs.append(f"monster:{normalized_id}")
                entry = self._load_monster(normalized_id)
                if entry is not None:
                    monsters.append(entry.to_prompt_entry())
                    sources.extend(self._source_payloads(entry.sources, "monsters", normalized_id))
        for card in combat.get("hand") or []:
            card_id = card.get("card_id") or card.get("id")
            if card_id:
                normalized_id = str(card_id)
                refs.append(f"card:{normalized_id}")
                entry = self._load_card(normalized_id)
                if entry is not None:
                    cards.append(entry.to_prompt_entry())
                    sources.extend(self._source_payloads(entry.sources, "cards", normalized_id))

        choice_cards: list[dict[str, Any]] = []
        if state.screen == "REWARD":
            reward = raw.get("reward") if isinstance(raw.get("reward"), dict) else {}
            choice_cards = [card for card in reward.get("cards") or [] if isinstance(card, dict)]
        elif state.screen == "SHOP":
            shop = raw.get("shop") if isinstance(raw.get("shop"), dict) else {}
            choice_cards = [card for card in shop.get("cards") or [] if isinstance(card, dict)]

        for card in choice_cards:
            card_id = card.get("card_id") or card.get("id")
            if not card_id:
                continue
            normalized_id = str(card_id)
            refs.append(f"card:{normalized_id}")
            card_entry = self._load_card(normalized_id)
            if card_entry is not None:
                cards.append(card_entry.to_prompt_entry())
                sources.extend(self._source_payloads(card_entry.sources, "cards", normalized_id))
            priority_entry = self._load_card_priority(normalized_id)
            if priority_entry is not None:
                refs.append(f"card_priority:{normalized_id}")
                card_priorities.append(priority_entry.to_prompt_entry())
                sources.extend(self._source_payloads(priority_entry.sources, "strategy/card_priorities", normalized_id))

        run = raw.get("run") if isinstance(raw.get("run"), dict) else {}
        for potion in run.get("potions") or []:
            potion_id = potion.get("potion_id")
            if potion_id:
                refs.append(f"potion:{potion_id}")

        event = raw.get("event") if isinstance(raw.get("event"), dict) else {}
        event_id = event.get("event_id") or event.get("id")
        if event_id:
            normalized_id = str(event_id)
            refs.append(f"event:{normalized_id}")
            entry = self._load_event(normalized_id)
            if entry is not None:
                events.append(entry.to_prompt_entry())
                sources.extend(self._source_payloads(entry.sources, "events", normalized_id))

        return KnowledgeContext(
            run_id=state.run_id,
            refs=sorted(set(refs)),
            cards=_deduplicate_entries(cards, "card_id"),
            card_priorities=_deduplicate_entries(card_priorities, "card_id"),
            monsters=_deduplicate_entries(monsters, "enemy_id"),
            events=_deduplicate_entries(events, "event_id"),
            sources=_deduplicate_entries(sources, "ref"),
        )

    def _load_monster(self, enemy_id: str) -> MonsterKnowledgeFile | None:
        if enemy_id not in self._monster_cache:
            self._monster_cache[enemy_id] = self._load_json(self._root_dir / "monsters" / f"{enemy_id}.json", MonsterKnowledgeFile)
        return self._monster_cache[enemy_id]

    def _load_event(self, event_id: str) -> EventKnowledgeFile | None:
        if event_id not in self._event_cache:
            self._event_cache[event_id] = self._load_json(self._root_dir / "events" / f"{event_id}.json", EventKnowledgeFile)
        return self._event_cache[event_id]

    def _load_card(self, card_id: str) -> CardKnowledgeFile | None:
        if card_id not in self._card_cache:
            self._card_cache[card_id] = self._load_json(self._root_dir / "cards" / f"{card_id}.json", CardKnowledgeFile)
        return self._card_cache[card_id]

    def _load_card_priority(self, card_id: str) -> CardPriorityKnowledgeFile | None:
        if card_id not in self._card_priority_cache:
            self._card_priority_cache[card_id] = self._load_json(
                self._root_dir / "strategy" / "card_priorities" / f"{card_id}.json",
                CardPriorityKnowledgeFile,
            )
        return self._card_priority_cache[card_id]

    @staticmethod
    def _source_payloads(sources: list[KnowledgeSource], category: str, entry_id: str) -> list[dict[str, Any]]:
        knowledge_path = f"{category}/{entry_id}.json"
        return [{**source.model_dump(), "knowledge_path": knowledge_path} for source in sources]

    @staticmethod
    def _load_json(
        path: Path,
        model_type: type[MonsterKnowledgeFile] | type[EventKnowledgeFile] | type[CardKnowledgeFile] | type[CardPriorityKnowledgeFile],
    ) -> MonsterKnowledgeFile | EventKnowledgeFile | CardKnowledgeFile | CardPriorityKnowledgeFile | None:
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as handle:
            return model_type.model_validate(json.load(handle))


def _deduplicate_entries(entries: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for entry in entries:
        value = entry.get(key)
        if not isinstance(value, str) or value in seen:
            continue
        seen.add(value)
        result.append(entry)
    return result
