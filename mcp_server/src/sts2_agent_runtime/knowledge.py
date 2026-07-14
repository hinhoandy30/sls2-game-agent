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


class KnowledgeProvider:
    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or Path(__file__).resolve().parents[2] / "data" / "knowledge" / "v1"
        self._monster_cache: dict[str, MonsterKnowledgeFile | None] = {}
        self._event_cache: dict[str, EventKnowledgeFile | None] = {}

    def for_state(self, state: GameStateSnapshot) -> KnowledgeContext:
        raw = state.state
        refs: list[str] = []
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
                refs.append(f"card:{card_id}")

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

    @staticmethod
    def _source_payloads(sources: list[KnowledgeSource], category: str, entry_id: str) -> list[dict[str, Any]]:
        knowledge_path = f"{category}/{entry_id}.json"
        return [{**source.model_dump(), "knowledge_path": knowledge_path} for source in sources]

    @staticmethod
    def _load_json(path: Path, model_type: type[MonsterKnowledgeFile] | type[EventKnowledgeFile]) -> MonsterKnowledgeFile | EventKnowledgeFile | None:
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
