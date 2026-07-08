from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from sts2_agent_runtime.client import is_actionable_state
from sts2_agent_runtime.contracts import ActionResult, AgentAction, GameStateSnapshot
from sts2_agent_runtime.runtime import AgentRuntime, RuntimeConfig, ValidationError
from sts2_agent_runtime.policies import EventPolicy, MapPolicy


def state_payload(
    *,
    screen: str,
    actions: list[str],
    combat: dict[str, Any] | None = None,
    run: dict[str, Any] | None = None,
    turn: int | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "data": {
            "state_version": 10,
            "run_id": "test_run",
            "screen": screen,
            "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
            "turn": turn,
            "available_actions": actions,
            "combat": combat,
            "run": run,
            "agent_view": {
                "version": 4,
                "screen": screen,
                "run_id": "test_run",
                "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
                "turn": turn,
                "available_actions": actions,
            },
        },
    }


def combat_payload(*, actions: list[str], hand: list[dict[str, Any]], enemy_hp: int = 30, energy: int = 3) -> dict[str, Any]:
    return state_payload(
        screen="COMBAT",
        actions=actions,
        turn=1,
        run={"floor": 1, "current_hp": 70, "potions": []},
        combat={
            "player": {"current_hp": 70, "max_hp": 80, "energy": energy, "block": 0},
            "hand": hand,
            "enemies": [{"index": 0, "enemy_id": "TEST_ENEMY", "current_hp": enemy_hp, "is_alive": True, "is_hittable": True}],
        },
    )


class DummyClient:
    def __init__(self, states: list[dict[str, Any]]) -> None:
        self.states = list(states)
        self.actions: list[AgentAction] = []
        self.wait_calls = 0

    def health(self) -> dict[str, Any]:
        return {"ok": True, "data": {"game_version": "v0.107.1", "mod_version": "test"}}

    def get_state(self) -> dict[str, Any]:
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def get_available_actions(self) -> list[dict[str, Any]]:
        state = self.get_state()["data"]
        return [{"name": name} for name in state["available_actions"]]

    def act(self, action: AgentAction) -> ActionResult:
        self.actions.append(action)
        return ActionResult(ok=True, action=action.action, status="completed", stable=True, message="ok", state=self.get_state()["data"])

    def wait_until_actionable(self, timeout_seconds: float) -> dict[str, Any]:
        self.wait_calls += 1
        return self.get_state()


class AgentRuntimeTests(unittest.TestCase):
    def test_combat_state_with_only_side_actions_is_not_actionable(self) -> None:
        payload = combat_payload(actions=["save_and_quit", "use_potion", "discard_potion"], hand=[])

        self.assertFalse(is_actionable_state(payload))

    def test_validate_rejects_stale_card_index(self) -> None:
        runtime = AgentRuntime(client=DummyClient([]))
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card"],
                hand=[{"index": 0, "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )

        with self.assertRaises(ValidationError) as cm:
            runtime.validate_action(snapshot, AgentAction("play_card", card_index=3, target_index=0))

        self.assertEqual(cm.exception.code, "stale_card_index")

    def test_validate_uses_hand_target_fields_not_action_tool_summary(self) -> None:
        runtime = AgentRuntime(client=DummyClient([]))
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card"],
                hand=[{"index": 0, "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )

        with self.assertRaises(ValidationError) as cm:
            runtime.validate_action(snapshot, AgentAction("play_card", card_index=0))

        self.assertEqual(cm.exception.code, "invalid_target_index")

    def test_validate_allows_map_potion_when_state_exposes_it(self) -> None:
        runtime = AgentRuntime(client=DummyClient([]))
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="MAP",
                actions=["choose_map_node", "use_potion"],
                run={
                    "floor": 2,
                    "potions": [
                        {"index": 0, "potion_id": "BLOOD_POTION", "occupied": True, "can_use": True, "can_discard": True, "requires_target": False}
                    ],
                },
            ),
            source="test",
        )

        runtime.validate_action(snapshot, AgentAction("use_potion", potion_index=0))

    def test_runtime_waits_after_action_response_without_action_window(self) -> None:
        passive_after_action = combat_payload(
            actions=["save_and_quit", "use_potion", "discard_potion"],
            hand=[{"index": 0, "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
        )
        fresh_actionable = combat_payload(
            actions=["end_turn", "play_card", "save_and_quit"],
            hand=[{"index": 0, "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
        )
        client = DummyClient([fresh_actionable, passive_after_action, fresh_actionable])
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(
                client=client,
                config=RuntimeConfig(max_steps=1, output_dir=Path(tmp), wait_timeout_seconds=1.0),
            )
            runtime.run()

        self.assertEqual(client.actions[0].action, "play_card")
        self.assertEqual(client.wait_calls, 1)

    def test_map_policy_prefers_monster_node(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="MAP",
                actions=["choose_map_node"],
                run={"floor": 1, "potions": []},
            ),
            source="test",
        )
        snapshot.state["map"] = {
            "available_nodes": [
                {"index": 0, "node_type": "Event"},
                {"index": 1, "node_type": "Monster"},
            ]
        }

        decision = MapPolicy().decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(decision.action.option_index, 1)

    def test_event_policy_supplies_option_index(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="EVENT",
                actions=["choose_event_option"],
                run={"floor": 1, "potions": []},
            ),
            source="test",
        )
        snapshot.state["event"] = {
            "event_id": "NEOW",
            "options": [
                {"index": 0, "is_locked": False},
                {"index": 1, "is_locked": False},
            ],
        }

        decision = EventPolicy().decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(decision.action.action, "choose_event_option")
        self.assertEqual(decision.action.option_index, 1)


if __name__ == "__main__":
    unittest.main()
