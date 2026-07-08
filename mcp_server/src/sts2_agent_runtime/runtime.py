from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import GameClient, GameClientError, action_names, is_actionable_state, unwrap_data
from .contracts import (
    SCHEMA_VERSION,
    ActionResult,
    AgentAction,
    GameStateSnapshot,
    PolicyDecision,
    RunSummary,
    StepRecord,
    utc_now_iso,
)
from .knowledge import KnowledgeProvider
from .policies import ScreenRouter


@dataclass(slots=True)
class RuntimeConfig:
    max_steps: int = 100
    wait_timeout_seconds: float = 20.0
    output_dir: Path = Path("runs")
    stop_after_first_combat: bool = False
    stop_on_reward_after_combat: bool = False
    max_consecutive_errors: int = 3


class ValidationError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_error(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


class AgentRuntime:
    def __init__(
        self,
        *,
        client: GameClient,
        config: RuntimeConfig | None = None,
        knowledge: KnowledgeProvider | None = None,
        router: ScreenRouter | None = None,
    ) -> None:
        self.client = client
        self.config = config or RuntimeConfig()
        self.knowledge = knowledge or KnowledgeProvider()
        self.router = router or ScreenRouter()
        self.health_payload: dict[str, Any] = {}
        self.records: list[StepRecord] = []

    def run(self) -> RunSummary:
        self.health_payload = self.client.health()
        state = self._snapshot(self.client.get_state())
        run_dir = self._run_dir(state.run_id)
        trajectory_path = run_dir / "trajectory.jsonl"
        error_count = 0
        terminal_reason = "max_steps_reached"

        for step_index in range(self.config.max_steps):
            try:
                state = self._ensure_actionable(state)
                if state.screen == "GAME_OVER":
                    terminal_reason = "game_over"
                    break

                knowledge = self.knowledge.for_state(state)
                decision = self.router.select(state).decide(state, knowledge)
                if decision.type in {"stop", "needs_human"}:
                    terminal_reason = decision.reason or decision.type
                    record = self._record(step_index, state, knowledge.refs, decision, None, None)
                    self._append_record(trajectory_path, record)
                    break
                if decision.type == "wait":
                    waited = self.client.wait_until_actionable(self.config.wait_timeout_seconds)
                    state = self._snapshot(waited)
                    record = self._record(step_index, state, knowledge.refs, decision, None, None)
                    self._append_record(trajectory_path, record)
                    continue
                if decision.action is None:
                    raise ValidationError("missing_action", "Action decision did not include AgentAction.")

                self.validate_action(state, decision.action)
                result = self.client.act(decision.action)
                next_state_payload = result.state if result.state is not None else self.client.get_state()
                if not is_actionable_state(next_state_payload):
                    next_state_payload = self.client.wait_until_actionable(self.config.wait_timeout_seconds)
                next_state = self._snapshot(next_state_payload)

                record = self._record(step_index, state, knowledge.refs, decision, decision.action, result)
                self._append_record(trajectory_path, record)
                state = next_state

                if self.config.stop_on_reward_after_combat and state.screen == "REWARD":
                    terminal_reason = "reached_reward_after_combat"
                    break
                if self.config.stop_after_first_combat and state.screen == "COMBAT":
                    terminal_reason = "entered_combat"
                    break

                error_count = 0
            except (ValidationError, GameClientError) as exc:
                error_count += 1
                error = exc.to_error() if hasattr(exc, "to_error") else {"code": "runtime_error", "message": str(exc)}
                record = self._record(
                    step_index,
                    state,
                    [],
                    PolicyDecision.stop("runtime error"),
                    None,
                    None,
                    error=error,
                )
                self._append_record(trajectory_path, record)
                if error_count >= self.config.max_consecutive_errors:
                    terminal_reason = f"too_many_errors:{error.get('code')}"
                    break
                time.sleep(0.5)

        summary = self._summary(state, terminal_reason, len(self.records), error_count)
        self._write_summary(run_dir, summary)
        return summary

    def validate_action(self, state: GameStateSnapshot, action: AgentAction) -> None:
        if action.action not in state.available_actions:
            raise ValidationError(
                "unavailable_action",
                f"Action {action.action!r} is not available.",
                details={"available_actions": state.available_actions},
            )

        raw = state.state
        if action.action == "play_card":
            self._validate_card_action(raw, action)
        elif action.action in {"use_potion", "discard_potion"}:
            self._validate_potion_action(raw, action)
        elif action.action in _OPTION_ACTIONS:
            if action.option_index is None:
                raise ValidationError("missing_option_index", f"{action.action} requires option_index.")

    def _validate_card_action(self, raw: dict[str, Any], action: AgentAction) -> None:
        if action.card_index is None:
            raise ValidationError("missing_card_index", "play_card requires card_index.")
        hand = ((raw.get("combat") or {}).get("hand") or [])
        selected = next((card for card in hand if card.get("index") == action.card_index), None)
        if selected is None:
            raise ValidationError("stale_card_index", "card_index is absent from latest combat.hand.", details={"card_index": action.card_index})
        if not selected.get("playable", False):
            raise ValidationError("unplayable_card", "Selected card is not playable.", details={"card_index": action.card_index, "reason": selected.get("unplayable_reason")})
        valid_targets = selected.get("valid_target_indices") or []
        if selected.get("requires_target"):
            if action.target_index not in valid_targets:
                raise ValidationError("invalid_target_index", "target_index is not valid for selected card.", details={"target_index": action.target_index, "valid_target_indices": valid_targets})
        elif action.target_index is not None:
            raise ValidationError("unexpected_target_index", "Selected card does not require target_index.")

    def _validate_potion_action(self, raw: dict[str, Any], action: AgentAction) -> None:
        index = action.potion_index if action.potion_index is not None else action.option_index
        if index is None:
            raise ValidationError("missing_potion_index", f"{action.action} requires potion_index or option_index.")
        potions = ((raw.get("run") or {}).get("potions") or [])
        selected = next((potion for potion in potions if potion.get("index") == index), None)
        if selected is None or not selected.get("occupied", False):
            raise ValidationError("invalid_potion_index", "potion index is absent or empty.", details={"potion_index": index})
        expected_flag = "can_use" if action.action == "use_potion" else "can_discard"
        if not selected.get(expected_flag, False):
            raise ValidationError("potion_action_unavailable", f"Potion does not satisfy {expected_flag}.", details={"potion_index": index})
        valid_targets = selected.get("valid_target_indices") or []
        if selected.get("requires_target") and action.target_index not in valid_targets:
            raise ValidationError("invalid_potion_target", "target_index is not valid for selected potion.", details={"target_index": action.target_index, "valid_target_indices": valid_targets})

    def _ensure_actionable(self, state: GameStateSnapshot) -> GameStateSnapshot:
        if is_actionable_state(state.state):
            return state
        return self._snapshot(self.client.wait_until_actionable(self.config.wait_timeout_seconds))

    def _snapshot(self, payload: dict[str, Any]) -> GameStateSnapshot:
        return GameStateSnapshot.from_raw(payload, source="http", health=self.health_payload)

    def _record(
        self,
        step_index: int,
        state: GameStateSnapshot,
        knowledge_refs: list[str],
        decision: PolicyDecision,
        action: AgentAction | None,
        result: ActionResult | None,
        *,
        error: dict[str, Any] | None = None,
    ) -> StepRecord:
        record = StepRecord(
            schema_version=SCHEMA_VERSION,
            run_id=state.run_id,
            step_index=step_index,
            observed_at=utc_now_iso(),
            screen_before=state.screen,
            state_summary=_state_summary(state.state),
            knowledge_refs=knowledge_refs,
            decision=decision.to_dict(),
            action_request=action.to_request() if action is not None else None,
            action_result=result.to_dict() if result is not None else None,
            error=error,
        )
        self.records.append(record)
        return record

    def _append_record(self, path: Path, record: StepRecord) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")

    def _summary(self, state: GameStateSnapshot, reason: str, step_count: int, error_count: int) -> RunSummary:
        run = state.state.get("run") if isinstance(state.state.get("run"), dict) else {}
        return RunSummary(
            schema_version=SCHEMA_VERSION,
            run_id=state.run_id,
            result="stopped",
            floor_reached=run.get("floor"),
            terminal_screen=state.screen,
            terminal_reason=reason,
            step_count=step_count,
            error_count=error_count,
            observed_at=utc_now_iso(),
        )

    def _write_summary(self, run_dir: Path, summary: RunSummary) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _run_dir(self, run_id: str) -> Path:
        timestamp = utc_now_iso().replace(":", "").replace("-", "").split(".")[0].replace("Z", "")
        safe_run_id = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in run_id)
        return self.config.output_dir / f"{timestamp}_{safe_run_id}"


_OPTION_ACTIONS = {
    "choose_map_node",
    "resolve_rewards",
    "claim_reward",
    "choose_reward_card",
    "select_deck_card",
    "choose_treasure_relic",
    "choose_event_option",
    "choose_capstone_option",
    "choose_bundle",
    "choose_rest_option",
    "buy_card",
    "buy_relic",
    "buy_potion",
}


def _state_summary(raw: dict[str, Any]) -> dict[str, Any]:
    run = raw.get("run") if isinstance(raw.get("run"), dict) else {}
    combat = raw.get("combat") if isinstance(raw.get("combat"), dict) else {}
    return {
        "screen": raw.get("screen"),
        "floor": run.get("floor"),
        "player_hp": run.get("current_hp") or (combat.get("player") or {}).get("current_hp"),
        "turn": raw.get("turn"),
        "available_actions": action_names(raw),
        "enemy_ids": [enemy.get("enemy_id") for enemy in (combat.get("enemies") or []) if enemy.get("enemy_id")],
    }
