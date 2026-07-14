from __future__ import annotations

import json
import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import GameClient, action_names, is_actionable_state
from .contracts import (
    SCHEMA_VERSION,
    ActionResult,
    AgentAction,
    GameStateSnapshot,
    PolicyDecision,
    RunSummary,
    StepRecord,
    TrajectorySegment,
    utc_now_iso,
)
from .knowledge import KnowledgeProvider
from .legal_actions import build_legal_actions
from .policies import ScreenRouter
from .route_planning import build_route_planning_payload


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
        review_agent: Any | None = None,
        experience_repository: Any | None = None,
    ) -> None:
        self.client = client
        self.config = config or RuntimeConfig()
        self.knowledge = knowledge or KnowledgeProvider()
        self.router = router or ScreenRouter()
        self.context_store = getattr(self.router, "context_store", None)
        self.review_agent = review_agent
        self.experience_repository = experience_repository
        self.health_payload: dict[str, Any] = {}
        self.records: list[StepRecord] = []
        self.segments: list[TrajectorySegment] = []
        self.current_segment: TrajectorySegment | None = None
        self.token_usage: dict[str, int] = {}
        self.run_started_at: float | None = None
        self._last_context_marker: str | None = None

    def run(self) -> RunSummary:
        self.run_started_at = time.perf_counter()
        self.health_payload = self.client.health()
        state = self._snapshot(self.client.get_state())
        run_dir = self._run_dir(state.run_id)
        trajectory_path = run_dir / "trajectory.jsonl"
        segments_path = run_dir / "segments.jsonl"
        context_path = run_dir / "context.jsonl"
        self._append_context_snapshot(context_path, state)
        self._start_segment(
            state,
            segments_path,
            start_reason="continue_run" if state.screen != "MAIN_MENU" else "new_run",
            parent_segment_id=None,
        )
        error_count = 0
        terminal_reason = "max_steps_reached"

        for step_index in range(self.config.max_steps):
            decision: PolicyDecision | None = None
            step_started_at = time.perf_counter()
            try:
                state = self._ensure_actionable(state)
                self._append_context_snapshot(context_path, state)
                if state.screen == "GAME_OVER":
                    terminal_reason = "game_over"
                    break

                knowledge = self.knowledge.for_state(state)
                decision = self.router.select(state).decide(state, knowledge)
                self._accumulate_decision_usage(decision)
                if decision.type in {"stop", "needs_human"}:
                    terminal_reason = decision.reason or decision.type
                    record = self._record(step_index, state, knowledge.refs, decision, None, None, step_started_at=step_started_at)
                    self._append_record(trajectory_path, record)
                    break
                if decision.type == "wait":
                    previous_state = state
                    waited = self.client.wait_until_actionable(self.config.wait_timeout_seconds)
                    state = self._snapshot(waited)
                    record = self._record(step_index, previous_state, knowledge.refs, decision, None, None, step_started_at=step_started_at, next_state=state)
                    self._append_record(trajectory_path, record)
                    continue
                if decision.action_plan:
                    next_state, executed_actions, results, plan_stop_reason = self._execute_action_plan(
                        state,
                        decision.action_plan,
                        tactical_boundary=_tactical_replan_boundary(decision),
                    )
                    if plan_stop_reason:
                        decision.metadata["plan_stop_reason"] = plan_stop_reason
                    record = self._record(
                        step_index,
                        state,
                        knowledge.refs,
                        decision,
                        executed_actions,
                        results,
                        step_started_at=step_started_at,
                        next_state=next_state,
                    )
                    self._append_record(trajectory_path, record)
                    self._maybe_start_segment_after_continue(state, next_state, executed_actions, segments_path)
                    state = next_state

                    if self.config.stop_on_reward_after_combat and state.screen == "REWARD":
                        terminal_reason = "reached_reward_after_combat"
                        break
                    if self.config.stop_after_first_combat and state.screen == "COMBAT":
                        terminal_reason = "entered_combat"
                        break

                    error_count = 0
                    continue

                if decision.action is None:
                    raise ValidationError("missing_action", "Action decision did not include AgentAction.")

                self.validate_action(state, decision.action)
                result = self.client.act(decision.action)
                next_state_payload = result.state if result.state is not None else self.client.get_state()
                if not is_actionable_state(next_state_payload):
                    next_state_payload = self.client.wait_until_actionable(self.config.wait_timeout_seconds)
                next_state = self._snapshot(next_state_payload)

                record = self._record(step_index, state, knowledge.refs, decision, decision.action, result, step_started_at=step_started_at, next_state=next_state)
                self._append_record(trajectory_path, record)
                self._maybe_start_segment_after_continue(state, next_state, decision.action, segments_path)
                state = next_state

                if self.config.stop_on_reward_after_combat and state.screen == "REWARD":
                    terminal_reason = "reached_reward_after_combat"
                    break
                if self.config.stop_after_first_combat and state.screen == "COMBAT":
                    terminal_reason = "entered_combat"
                    break

                error_count = 0
            except Exception as exc:
                error_count += 1
                error = exc.to_error() if hasattr(exc, "to_error") else {
                    "code": "policy_error",
                    "message": str(exc),
                    "details": {"exception_type": exc.__class__.__name__},
                }
                record = self._record(
                    step_index,
                    state,
                    [],
                    decision or PolicyDecision.stop("runtime error"),
                    _decision_actions(decision) if decision is not None else None,
                    None,
                    step_started_at=step_started_at,
                    error=error,
                )
                self._append_record(trajectory_path, record)
                if error_count >= self.config.max_consecutive_errors:
                    terminal_reason = f"too_many_errors:{error.get('code')}"
                    break
                time.sleep(0.5)

        duration_seconds = round(time.perf_counter() - self.run_started_at, 6) if self.run_started_at is not None else None
        summary = self._summary(state, terminal_reason, len(self.records), error_count, duration_seconds=duration_seconds)
        self._review_game_over(run_dir, summary)
        self._write_summary(run_dir, summary)
        return summary

    def validate_action(self, state: GameStateSnapshot, action: AgentAction) -> None:
        if action.legal_action_id is not None:
            legal_ids = {str(legal.get("id")) for legal in build_legal_actions(state)}
            if action.legal_action_id not in legal_ids:
                raise ValidationError(
                    "unavailable_legal_action",
                    "legal_action_id is not available in the latest state.",
                    details={"legal_action_id": action.legal_action_id},
                )

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
        hand = ((raw.get("combat") or {}).get("hand") or [])
        if action.card_instance_id is not None:
            selected = next((card for card in hand if card.get("card_instance_id") == action.card_instance_id), None)
            if selected is None:
                raise ValidationError(
                    "stale_card_instance_id",
                    "card_instance_id is absent from latest combat.hand.",
                    details={"card_instance_id": action.card_instance_id},
                )
            selected_index = selected.get("index")
            if isinstance(selected_index, int):
                action.card_index = selected_index
        else:
            if action.card_index is None:
                raise ValidationError("missing_card_index", "play_card requires card_instance_id or card_index.")
            selected = next((card for card in hand if card.get("index") == action.card_index), None)
        if selected is None:
            raise ValidationError("stale_card_index", "card_index is absent from latest combat.hand.", details={"card_index": action.card_index})
        if not selected.get("playable", False):
            raise ValidationError("unplayable_card", "Selected card is not playable.", details={"card_index": action.card_index, "reason": selected.get("unplayable_reason")})
        valid_targets = selected.get("valid_target_indices") or []
        if selected.get("requires_target"):
            if action.target_instance_id is not None:
                enemies = ((raw.get("combat") or {}).get("enemies") or [])
                target = next((enemy for enemy in enemies if enemy.get("enemy_instance_id") == action.target_instance_id), None)
                if target is None:
                    raise ValidationError(
                        "stale_target_instance_id",
                        "target_instance_id is absent from latest combat.enemies.",
                        details={"target_instance_id": action.target_instance_id},
                    )
                target_index = target.get("index")
                if not isinstance(target_index, int) or target_index not in valid_targets:
                    raise ValidationError(
                        "invalid_target_instance_id",
                        "target_instance_id is not a valid target for selected card.",
                        details={"target_instance_id": action.target_instance_id, "valid_target_indices": valid_targets},
                    )
                action.target_index = target_index
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
        if selected.get("requires_target"):
            if action.target_instance_id is not None:
                enemies = ((raw.get("combat") or {}).get("enemies") or [])
                target = next((enemy for enemy in enemies if enemy.get("enemy_instance_id") == action.target_instance_id), None)
                if target is None:
                    raise ValidationError(
                        "stale_target_instance_id",
                        "target_instance_id is absent from latest combat.enemies.",
                        details={"target_instance_id": action.target_instance_id},
                    )
                target_index = target.get("index")
                if not isinstance(target_index, int) or target_index not in valid_targets:
                    raise ValidationError(
                        "invalid_target_instance_id",
                        "target_instance_id is not a valid target for selected potion.",
                        details={"target_instance_id": action.target_instance_id, "valid_target_indices": valid_targets},
                    )
                action.target_index = target_index
            if action.target_index not in valid_targets:
                raise ValidationError("invalid_potion_target", "target_index is not valid for selected potion.", details={"target_index": action.target_index, "valid_target_indices": valid_targets})

    def _execute_action_plan(
        self,
        state: GameStateSnapshot,
        actions: list[AgentAction],
        *,
        tactical_boundary: tuple[str, str] | None = None,
    ) -> tuple[GameStateSnapshot, list[AgentAction], list[ActionResult], str | None]:
        current_state = state
        initial_screen = state.screen
        executed_actions: list[AgentAction] = []
        results: list[ActionResult] = []
        stop_reason: str | None = None

        for action_index, action in enumerate(actions):
            try:
                self.validate_action(current_state, action)
            except ValidationError as exc:
                if action_index == 0:
                    raise
                stop_reason = f"validation_stopped:{exc.code}"
                break

            result = self.client.act(action)
            next_state_payload = result.state if result.state is not None else self.client.get_state()
            if not is_actionable_state(next_state_payload):
                next_state_payload = self.client.wait_until_actionable(self.config.wait_timeout_seconds)
            current_state = self._snapshot(next_state_payload)
            executed_actions.append(action)
            results.append(result)

            if tactical_boundary is not None and action.legal_action_id == tactical_boundary[0]:
                stop_reason = f"tactical_replan:{tactical_boundary[1]}"
                break

            if current_state.screen != initial_screen:
                stop_reason = f"screen_changed:{current_state.screen}"
                break
            if current_state.screen != "COMBAT":
                stop_reason = f"non_combat_screen:{current_state.screen}"
                break

        if not executed_actions:
            raise ValidationError("empty_action_plan", "Action plan did not execute any actions.")
        return current_state, executed_actions, results, stop_reason

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
        action: AgentAction | list[AgentAction] | None,
        result: ActionResult | list[ActionResult] | None,
        *,
        step_started_at: float | None = None,
        error: dict[str, Any] | None = None,
        next_state: GameStateSnapshot | None = None,
    ) -> StepRecord:
        metrics = _step_metrics(step_started_at, decision)
        record = StepRecord(
            schema_version=SCHEMA_VERSION,
            run_id=state.run_id,
            segment_id=self.current_segment.segment_id if self.current_segment is not None else "segment_unknown",
            step_index=step_index,
            observed_at=utc_now_iso(),
            screen_before=state.screen,
            state_hash_before=_state_hash(state.state),
            state_hash_after=_state_hash(next_state.state) if next_state is not None else None,
            state_summary=_state_summary(state.state),
            knowledge_refs=knowledge_refs,
            decision=decision.to_dict(),
            action_request=_action_request_payload(action),
            action_result=_action_result_payload(result),
            error=error,
            metrics=metrics,
        )
        self.records.append(record)
        return record

    def _append_record(self, path: Path, record: StepRecord) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")

    def _summary(
        self,
        state: GameStateSnapshot,
        reason: str,
        step_count: int,
        error_count: int,
        *,
        duration_seconds: float | None,
    ) -> RunSummary:
        run = state.state.get("run") if isinstance(state.state.get("run"), dict) else {}
        return RunSummary(
            schema_version=SCHEMA_VERSION,
            run_id=state.run_id,
            result="loss" if state.screen == "GAME_OVER" else "stopped",
            floor_reached=run.get("floor"),
            terminal_screen=state.screen,
            terminal_reason=reason,
            step_count=step_count,
            error_count=error_count,
            observed_at=utc_now_iso(),
            duration_seconds=duration_seconds,
            token_usage=dict(self.token_usage),
            segment_count=len(self.segments),
        )

    def _write_summary(self, run_dir: Path, summary: RunSummary) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_context_snapshot(self, path: Path, state: GameStateSnapshot) -> None:
        if self.context_store is None:
            return
        snapshot = self.context_store.snapshot(state)
        marker = snapshot.get("snapshot_marker")
        if isinstance(marker, str) and marker == self._last_context_marker:
            return
        self._last_context_marker = marker if isinstance(marker, str) else None
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _review_game_over(self, run_dir: Path, summary: RunSummary) -> None:
        if summary.terminal_screen != "GAME_OVER" or self.review_agent is None:
            return
        try:
            result = self.review_agent.review(run_dir, summary)
            review_path = run_dir / "review.json"
            review_path.write_text(json.dumps(result.report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if self.experience_repository is not None:
                self.experience_repository.save_lessons(result.report.lessons)
            summary.review_path = review_path.name
            summary.experience_lesson_count = len(result.report.lessons)
            usage = result.llm_metadata.get("usage") if isinstance(result.llm_metadata, dict) else None
            if isinstance(usage, dict):
                for key, value in usage.items():
                    if isinstance(value, int):
                        self.token_usage[key] = self.token_usage.get(key, 0) + value
                summary.token_usage = dict(self.token_usage)
        except Exception as exc:
            summary.review_error = {
                "code": "review_error",
                "message": str(exc),
                "details": {"exception_type": exc.__class__.__name__},
            }

    def _run_dir(self, run_id: str) -> Path:
        timestamp = utc_now_iso().replace(":", "").replace("-", "").split(".")[0].replace("Z", "")
        safe_run_id = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in run_id)
        return self.config.output_dir / f"{timestamp}_{safe_run_id}"

    def _accumulate_decision_usage(self, decision: PolicyDecision) -> None:
        llm = decision.metadata.get("llm") if isinstance(decision.metadata, dict) else None
        if not isinstance(llm, dict):
            return
        usage = llm.get("usage")
        if not isinstance(usage, dict):
            return
        for key, value in usage.items():
            if isinstance(value, int):
                self.token_usage[key] = self.token_usage.get(key, 0) + value

    def _start_segment(
        self,
        state: GameStateSnapshot,
        path: Path,
        *,
        start_reason: str,
        parent_segment_id: str | None,
    ) -> None:
        run = state.state.get("run") if isinstance(state.state.get("run"), dict) else {}
        segment = TrajectorySegment(
            schema_version=SCHEMA_VERSION,
            segment_id=f"seg_{uuid.uuid4().hex[:12]}",
            run_id=state.run_id,
            parent_segment_id=parent_segment_id,
            start_reason=start_reason,
            checkpoint_hash=_state_hash(state.state),
            start_floor=run.get("floor"),
            start_screen=state.screen,
            start_hp=run.get("current_hp") or ((state.state.get("combat") or {}).get("player") or {}).get("current_hp"),
            observed_at=utc_now_iso(),
        )
        self.current_segment = segment
        self.segments.append(segment)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(segment.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")

    def _maybe_start_segment_after_continue(
        self,
        before: GameStateSnapshot,
        after: GameStateSnapshot,
        action: AgentAction | list[AgentAction],
        segments_path: Path,
    ) -> None:
        actions = action if isinstance(action, list) else [action]
        if not any(item.action == "continue_run" for item in actions):
            return
        if _state_hash(before.state) == _state_hash(after.state):
            return
        self._start_segment(
            after,
            segments_path,
            start_reason="retry_from_checkpoint",
            parent_segment_id=self.current_segment.segment_id if self.current_segment is not None else None,
        )


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
    snapshot = GameStateSnapshot.from_raw({"data": raw}, source="summary")
    legal_actions = build_legal_actions(snapshot)
    summary = {
        "screen": raw.get("screen"),
        "floor": run.get("floor"),
        "player_hp": run.get("current_hp") or (combat.get("player") or {}).get("current_hp"),
        "turn": raw.get("turn"),
        "available_actions": action_names(raw),
        "legal_action_ids": [str(action.get("id")) for action in legal_actions],
        "enemy_ids": [enemy.get("enemy_id") for enemy in (combat.get("enemies") or []) if enemy.get("enemy_id")],
    }
    if raw.get("screen") == "MAP":
        route_planning = build_route_planning_payload(raw, legal_actions)
        if route_planning is not None:
            summary["route_planning"] = _route_planning_summary(route_planning)
    if raw.get("screen") == "BUNDLE_SELECTION":
        summary["bundles"] = _bundle_summary(raw.get("bundles"))
    return summary


def _bundle_summary(bundles: Any) -> list[dict[str, Any]]:
    if not isinstance(bundles, list):
        return []
    summarized: list[dict[str, Any]] = []
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        cards: list[dict[str, Any]] = []
        for card in bundle.get("cards") or []:
            if not isinstance(card, dict):
                continue
            cards.append(
                {
                    "index": card.get("index"),
                    "card_id": card.get("card_id"),
                    "name": card.get("name"),
                    "card_type": card.get("card_type"),
                    "rarity": card.get("rarity"),
                    "energy_cost": card.get("energy_cost"),
                    "resolved_rules_text": card.get("resolved_rules_text"),
                }
            )
        summarized.append({"index": bundle.get("index"), "cards": cards})
    return summarized


def _route_planning_summary(route_planning: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": route_planning.get("schema_version"),
        "map_generation_count": route_planning.get("map_generation_count"),
        "current_node_id": route_planning.get("current_node_id"),
        "available_node_ids": route_planning.get("available_node_ids"),
        "route_count": route_planning.get("route_count"),
        "routes_omitted": route_planning.get("routes_omitted"),
        "route_groups": route_planning.get("route_groups") or [],
        "route_candidates": [
            {
                "route_id": candidate.get("route_id"),
                "next_node_id": candidate.get("next_node_id"),
                "next_legal_action_id": candidate.get("next_legal_action_id"),
                "remaining_sequence": candidate.get("remaining_sequence"),
                "remaining_counts": candidate.get("remaining_counts"),
                "features": candidate.get("features"),
            }
            for candidate in route_planning.get("route_candidates") or []
            if isinstance(candidate, dict)
        ],
    }


def _step_metrics(step_started_at: float | None, decision: PolicyDecision) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if step_started_at is not None:
        metrics["step_duration_seconds"] = round(time.perf_counter() - step_started_at, 6)
    llm = decision.metadata.get("llm") if isinstance(decision.metadata, dict) else None
    if isinstance(llm, dict) and llm:
        metrics["llm"] = llm
    return metrics


def _decision_actions(decision: PolicyDecision) -> AgentAction | list[AgentAction] | None:
    if decision.action_plan:
        return decision.action_plan
    return decision.action


def _tactical_replan_boundary(decision: PolicyDecision) -> tuple[str, str] | None:
    """Return the earliest LLM-declared information boundary, if its audit was validated."""
    audit = decision.metadata.get("combat_audit") if isinstance(decision.metadata, dict) else None
    if not isinstance(audit, dict):
        return None
    boundaries = audit.get("replan_after")
    if not isinstance(boundaries, list) or not boundaries:
        return None
    boundary = boundaries[0]
    if not isinstance(boundary, dict):
        return None
    action_id = boundary.get("legal_action_id")
    reason = boundary.get("reason")
    if not isinstance(action_id, str) or not isinstance(reason, str):
        return None
    return action_id, reason


def _action_request_payload(action: AgentAction | list[AgentAction] | None) -> dict[str, Any] | None:
    if action is None:
        return None
    if isinstance(action, list):
        return {"action_plan": [_action_to_log_request(item) for item in action]}
    return _action_to_log_request(action)


def _action_result_payload(result: ActionResult | list[ActionResult] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    if isinstance(result, list):
        return {"action_results": [item.to_dict() for item in result]}
    return result.to_dict()


def _action_to_log_request(action: AgentAction) -> dict[str, Any]:
    payload = action.to_request()
    if action.legal_action_id is not None:
        payload["legal_action_id"] = action.legal_action_id
    return payload


def _state_hash(raw: dict[str, Any]) -> str:
    canonical = json.dumps(_hashable_state(raw), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _hashable_state(raw: dict[str, Any]) -> dict[str, Any]:
    run = raw.get("run") if isinstance(raw.get("run"), dict) else {}
    combat = raw.get("combat") if isinstance(raw.get("combat"), dict) else {}
    return {
        "run_id": raw.get("run_id"),
        "screen": raw.get("screen"),
        "turn": raw.get("turn"),
        "available_actions": action_names(raw),
        "run": {
            "floor": run.get("floor"),
            "hp": run.get("current_hp"),
            "max_hp": run.get("max_hp"),
            "gold": run.get("gold"),
            "deck": [(card.get("card_id"), card.get("upgraded")) for card in run.get("deck") or [] if isinstance(card, dict)],
            "potions": [(potion.get("index"), potion.get("potion_id"), potion.get("occupied")) for potion in run.get("potions") or [] if isinstance(potion, dict)],
            "relics": [relic.get("relic_id") for relic in run.get("relics") or [] if isinstance(relic, dict)],
        },
        "combat": {
            "player": {
                "hp": (combat.get("player") or {}).get("current_hp"),
                "block": (combat.get("player") or {}).get("block"),
                "energy": (combat.get("player") or {}).get("energy"),
            },
            "hand": [
                (card.get("index"), card.get("card_id"), card.get("upgraded"), card.get("playable"))
                for card in combat.get("hand") or []
                if isinstance(card, dict)
            ],
            "enemies": [
                (enemy.get("index"), enemy.get("enemy_id"), enemy.get("current_hp"), enemy.get("block"), enemy.get("is_alive"), enemy.get("intent"))
                for enemy in combat.get("enemies") or []
                if isinstance(enemy, dict)
            ],
        },
        "map": (raw.get("map") or {}).get("current_node") if isinstance(raw.get("map"), dict) else None,
        "selection": (raw.get("selection") or {}).get("kind") if isinstance(raw.get("selection"), dict) else None,
    }
