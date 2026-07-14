from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SpecialistAgentName = Literal["route_strategy", "combat", "run_development"]


class StrategyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1, max_length=80)
    text_zh: str = Field(min_length=1, max_length=1200)


class SpecialistStrategy(BaseModel):
    """A human-maintained, versioned policy layer for one specialist agent."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sts2-specialist-strategy.v1"]
    agent_name: SpecialistAgentName
    strategy_id: str = Field(min_length=1, max_length=120)
    revision: int = Field(ge=1)
    title_zh: str = Field(min_length=1, max_length=160)
    rules_zh: list[StrategyRule] = Field(min_length=1, max_length=32)

    def render_instruction(self) -> str:
        rules = "\n".join(f"{index}. {rule.text_zh}" for index, rule in enumerate(self.rules_zh, start=1))
        return f"专项策略：{self.title_zh}\n{rules}"

    def metadata(self) -> dict[str, str | int]:
        canonical = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {
            "strategy_id": self.strategy_id,
            "strategy_revision": self.revision,
            "strategy_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
        }


class StrategyProvider:
    """Loads validated specialist strategies from a versioned data directory."""

    def __init__(self, root_dir: Path | None = None) -> None:
        configured_root = os.getenv("STS2_STRATEGY_DIR")
        self._root_dir = root_dir or (Path(configured_root) if configured_root else Path(__file__).resolve().parents[2] / "data" / "strategies" / "v1")
        self._cache: dict[str, SpecialistStrategy] = {}

    def get(self, agent_name: SpecialistAgentName) -> SpecialistStrategy:
        cached = self._cache.get(agent_name)
        if cached is not None:
            return cached

        path = self._root_dir / f"{agent_name}.json"
        if not path.is_file():
            raise RuntimeError(f"Missing strategy file for {agent_name}: {path}")
        try:
            with path.open(encoding="utf-8") as handle:
                strategy = SpecialistStrategy.model_validate(json.load(handle))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"Invalid strategy file for {agent_name}: {path}: {exc}") from exc
        if strategy.agent_name != agent_name:
            raise RuntimeError(f"Strategy file {path} declares {strategy.agent_name!r}, expected {agent_name!r}.")

        self._cache[agent_name] = strategy
        return strategy

