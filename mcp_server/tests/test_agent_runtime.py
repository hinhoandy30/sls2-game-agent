from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from sts2_agent_runtime.client import is_actionable_state
from sts2_agent_runtime.cli import _load_env_file, _port_from_base_url, enable_instant_mode
from sts2_agent_runtime.contracts import ActionResult, AgentAction, GameStateSnapshot, PolicyDecision
from sts2_agent_runtime.action_spec import action_spec_prompt_options, parse_llm_action_payload, parse_llm_action_plan_payload
from sts2_agent_runtime.legal_actions import build_legal_actions
from sts2_agent_runtime.llm import OpenAICompatiblePolicy
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
            "enemies": [{"index": 0, "enemy_instance_id": "enemy_1", "enemy_id": "TEST_ENEMY", "current_hp": enemy_hp, "is_alive": True, "is_hittable": True}],
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


class ConsoleClient:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run_console_command(self, command: str) -> ActionResult:
        self.commands.append(command)
        return ActionResult(ok=True, action="run_console_command", status="completed", stable=True, message="ok")


class RaisingPolicy:
    def decide(self, state: GameStateSnapshot, knowledge: Any) -> Any:
        raise RuntimeError("model returned invalid JSON")


class StaticRouter:
    def select(self, state: GameStateSnapshot) -> RaisingPolicy:
        return RaisingPolicy()


class SinglePolicyRouter:
    def __init__(self, policy: Any) -> None:
        self.policy = policy

    def select(self, state: GameStateSnapshot) -> Any:
        return self.policy


class FakeLLMPolicy(OpenAICompatiblePolicy):
    def __init__(self, response: str | list[str], *, enable_action_plan: bool = False, max_plan_actions: int = 5) -> None:
        self.response = response
        self.enable_action_plan = enable_action_plan
        self.max_plan_actions = max_plan_actions
        self.max_retries = 2
        self.last_call_metadata = {}
        self.last_prompt: dict[str, Any] = {}

    def _chat(self, prompt: dict[str, Any]) -> str:
        self.last_prompt = prompt
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response


class MeteredFakeLLMPolicy(FakeLLMPolicy):
    def _chat(self, prompt: dict[str, Any]) -> str:
        self.last_call_metadata = {
            "provider": "test",
            "model": "fake-model",
            "duration_seconds": 0.25,
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
                "reasoning_tokens": 2,
            },
        }
        return self.response


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

    def test_runtime_records_policy_error_instead_of_crashing(self) -> None:
        client = DummyClient(
            [
                state_payload(
                    screen="MAP",
                    actions=["choose_map_node"],
                    run={"floor": 1, "potions": []},
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(
                client=client,
                router=StaticRouter(),
                config=RuntimeConfig(max_steps=3, output_dir=Path(tmp), max_consecutive_errors=2),
            )
            summary = runtime.run()

        self.assertEqual(summary.terminal_reason, "too_many_errors:policy_error")
        self.assertEqual(summary.error_count, 2)

    def test_load_env_file_does_not_override_existing_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "OPENAI_MODEL=from-file",
                        "OPENAI_API_BASE='https://example.test/v1'",
                    ]
                ),
                encoding="utf-8",
            )
            old_model = os.environ.get("OPENAI_MODEL")
            old_base = os.environ.get("OPENAI_API_BASE")
            try:
                os.environ["OPENAI_MODEL"] = "from-env"
                os.environ.pop("OPENAI_API_BASE", None)
                _load_env_file(env_path)

                self.assertEqual(os.environ["OPENAI_MODEL"], "from-env")
                self.assertEqual(os.environ["OPENAI_API_BASE"], "https://example.test/v1")
            finally:
                if old_model is None:
                    os.environ.pop("OPENAI_MODEL", None)
                else:
                    os.environ["OPENAI_MODEL"] = old_model
                if old_base is None:
                    os.environ.pop("OPENAI_API_BASE", None)
                else:
                    os.environ["OPENAI_API_BASE"] = old_base

    def test_llm_non_action_raises_when_actions_are_available(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card", "end_turn", "save_and_quit"],
                hand=[{"index": 0, "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )

        with self.assertRaises(ValueError):
            FakeLLMPolicy('{"type":"needs_human","reason":"not sure"}').decide(snapshot, knowledge=type("K", (), {"refs": []})())

    def test_llm_accepts_action_shorthand(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(actions=["end_turn"], hand=[]),
            source="test",
        )

        decision = FakeLLMPolicy('{"action":"end_turn","reason":"done"}').decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(decision.type, "action")
        self.assertEqual(decision.action.action, "end_turn")

    def test_llm_accepts_legal_action_id(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(actions=["end_turn"], hand=[]),
            source="test",
        )

        decision = FakeLLMPolicy('{"legal_action_id":"end_turn","reason":"legal"}').decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(decision.type, "action")
        self.assertEqual(decision.action.action, "end_turn")
        self.assertEqual(decision.action.legal_action_id, "end_turn")

    def test_llm_repairs_malformed_json_response(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(actions=["end_turn"], hand=[]),
            source="test",
        )

        decision = FakeLLMPolicy(['{"type": action', '{"action":"end_turn","reason":"repaired"}']).decide(
            snapshot,
            knowledge=type("K", (), {"refs": []})(),
        )

        self.assertEqual(decision.type, "action")
        self.assertEqual(decision.action.action, "end_turn")
        self.assertEqual(decision.reason, "repaired")

    def test_llm_maps_option_action_card_index_to_option_index(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="CARD_SELECTION",
                actions=["select_deck_card"],
                run={"floor": 1, "potions": []},
            ),
            source="test",
        )

        decision = FakeLLMPolicy(
            '{"type":"action","action":{"action":"select_deck_card","card_index":5},"reason":"transform a defend"}'
        ).decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(decision.action.action, "select_deck_card")
        self.assertIsNone(decision.action.card_index)
        self.assertEqual(decision.action.option_index, 5)

    def test_llm_maps_option_action_target_index_to_option_index(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="MAP",
                actions=["choose_map_node"],
                run={"floor": 1, "potions": []},
            ),
            source="test",
        )

        decision = FakeLLMPolicy(
            '{"type":"action","action":{"action":"choose_map_node","target_index":2},"reason":"take node 2"}'
        ).decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(decision.action.action, "choose_map_node")
        self.assertIsNone(decision.action.target_index)
        self.assertEqual(decision.action.option_index, 2)

    def test_llm_infers_missing_map_option_index_from_state(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="MAP",
                actions=["choose_map_node"],
                run={"floor": 3, "potions": []},
            ),
            source="test",
        )
        snapshot.state["map"] = {"available_nodes": [{"index": 7, "node_type": "Unknown"}]}

        decision = FakeLLMPolicy('{"type":"action","action":{"action":"choose_map_node"},"reason":"only node"}').decide(
            snapshot,
            knowledge=type("K", (), {"refs": []})(),
        )

        self.assertEqual(decision.action.action, "choose_map_node")
        self.assertEqual(decision.action.option_index, 7)

    def test_action_spec_rejects_wrong_map_index_field_after_normalization_if_forbidden_remains(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="MAP",
                actions=["choose_map_node"],
                run={"floor": 1, "potions": []},
            ),
            source="test",
        )

        with self.assertRaises(ValueError):
            parse_llm_action_payload(
                {"action": "choose_map_node", "option_index": 0, "potion_index": 0},
                snapshot,
            )

    def test_action_spec_renders_available_map_options(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="MAP",
                actions=["choose_map_node", "save_and_quit"],
                run={"floor": 1, "potions": []},
            ),
            source="test",
        )
        snapshot.state["map"] = {"available_nodes": [{"index": 3, "node_type": "Monster", "row": 2, "col": 1}]}

        options = action_spec_prompt_options(snapshot)

        self.assertEqual(options[0]["action"], "choose_map_node")
        self.assertEqual(options[0]["required_params"], ["option_index"])
        self.assertEqual(options[0]["options"][0]["option_index"], 3)

    def test_action_plan_payload_validates_and_normalizes_actions(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="MAP",
                actions=["choose_map_node"],
                run={"floor": 1, "potions": []},
            ),
            source="test",
        )

        actions, stop_conditions = parse_llm_action_plan_payload(
            {
                "actions": [{"action": "choose_map_node", "target_index": 2}],
                "stop_conditions": ["screen_changes"],
            },
            snapshot,
        )

        self.assertEqual(actions[0].action, "choose_map_node")
        self.assertIsNone(actions[0].target_index)
        self.assertEqual(actions[0].option_index, 2)
        self.assertEqual(stop_conditions, ["screen_changes"])

    def test_legal_actions_include_only_usable_potion_slots(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="COMBAT",
                actions=["use_potion", "discard_potion", "end_turn"],
                run={
                    "floor": 1,
                    "current_hp": 70,
                    "potions": [
                        {"index": 0, "potion_id": "STABLE_SERUM", "name": "稳定血清", "occupied": True, "can_use": False, "can_discard": True},
                        {"index": 1, "potion_id": "FYSH_OIL", "name": "异鱼之油", "occupied": True, "can_use": True, "can_discard": True},
                    ],
                },
                combat={"player": {"current_hp": 70, "energy": 3}, "hand": [], "enemies": []},
                turn=1,
            ),
            source="test",
        )

        legal = build_legal_actions(snapshot)

        self.assertIn("use_potion_potion_1_FYSH-OIL", {item["id"] for item in legal})
        self.assertNotIn("use_potion_potion_0_STABLE-SERUM", {item["id"] for item in legal})

    def test_legal_actions_distinguish_identical_card_instances(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card"],
                hand=[
                    {"index": 0, "card_instance_id": "card_101", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]},
                    {"index": 1, "card_instance_id": "card_102", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]},
                ],
            ),
            source="test",
        )

        legal = [item for item in build_legal_actions(snapshot) if item["action"] == "play_card"]

        self.assertEqual({item["card_instance_id"] for item in legal}, {"card_101", "card_102"})
        self.assertEqual(len({item["id"] for item in legal}), 2)

    def test_llm_action_plan_decision_for_combat(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card", "end_turn"],
                hand=[{"index": 0, "card_instance_id": "card_101", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )
        legal_action_id = next(item["id"] for item in build_legal_actions(snapshot) if item["action"] == "play_card")

        decision = FakeLLMPolicy(
            '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + legal_action_id + '"},{"legal_action_id":"end_turn"}],"stop_conditions":["screen_changes"]},"reason":"attack then pass"}',
            enable_action_plan=True,
        ).decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(decision.type, "action")
        self.assertEqual(len(decision.action_plan), 2)
        self.assertEqual(decision.action_plan[0].action, "play_card")
        self.assertEqual(decision.action.action, "play_card")

    def test_llm_stable_combat_plan_prompt_uses_only_instance_legal_actions(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card", "end_turn"],
                hand=[{"index": 0, "card_instance_id": "card_101", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )
        play_id = next(item["id"] for item in build_legal_actions(snapshot) if item["action"] == "play_card")
        policy = FakeLLMPolicy(
            '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + play_id + '"},{"legal_action_id":"end_turn"}]},"reason":"two-step plan"}',
            enable_action_plan=True,
        )

        decision = policy.decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(decision.metadata["planning"]["mode"], "stable_action_plan")
        self.assertEqual(policy.last_prompt["planning_mode"], "stable_action_plan")
        self.assertEqual(policy.last_prompt["response_schema"]["action_plan"]["actions"], [{"legal_action_id": "required string id from plan_legal_actions"}])
        self.assertEqual({item["action"] for item in policy.last_prompt["plan_legal_actions"]}, {"play_card", "end_turn"})
        self.assertEqual(policy.last_prompt["legal_actions"], policy.last_prompt["plan_legal_actions"])
        self.assertNotIn("card_index", policy.last_prompt["response_schema"]["action_plan"])
        self.assertEqual(len(decision.action_plan), 2)

    def test_llm_falls_back_to_single_action_without_card_instance_id(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card", "end_turn"],
                hand=[{"index": 0, "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )
        legal_id = next(item["id"] for item in build_legal_actions(snapshot) if item["action"] == "play_card")
        policy = FakeLLMPolicy('{"legal_action_id":"' + legal_id + '","reason":"legacy bridge"}', enable_action_plan=True)

        decision = policy.decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(policy.last_prompt["planning_mode"], "single_action")
        self.assertEqual(policy.last_prompt["action_plan_rules"]["reason"], "card_instance_id_missing")
        self.assertEqual(decision.metadata["planning"]["gate_reason"], "card_instance_id_missing")
        self.assertTrue(decision.metadata["planning"]["fallback_from_stable_plan"])

    def test_enable_instant_mode_runs_console_command(self) -> None:
        client = ConsoleClient()

        result = enable_instant_mode(client, "instant")

        self.assertEqual(client.commands, ["instant"])
        self.assertEqual(result.action, "run_console_command")

    def test_debug_session_port_comes_from_base_url(self) -> None:
        self.assertEqual(_port_from_base_url("http://127.0.0.1:8080"), 8080)
        self.assertEqual(_port_from_base_url("http://127.0.0.1"), 80)

    def test_runtime_validation_error_keeps_attempted_action_record(self) -> None:
        class MissingOptionPolicy:
            def decide(self, state: GameStateSnapshot, knowledge: Any) -> Any:
                return PolicyDecision.action_decision(AgentAction("select_deck_card"), reason="missing option")

        class MissingOptionRouter:
            def select(self, state: GameStateSnapshot) -> MissingOptionPolicy:
                return MissingOptionPolicy()

        client = DummyClient(
            [
                state_payload(
                    screen="CARD_SELECTION",
                    actions=["select_deck_card"],
                    run={"floor": 1, "potions": []},
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(
                client=client,
                router=MissingOptionRouter(),
                config=RuntimeConfig(max_steps=1, output_dir=Path(tmp), max_consecutive_errors=1),
            )
            runtime.run()

        self.assertEqual(runtime.records[0].error["code"], "missing_option_index")
        self.assertEqual(runtime.records[0].action_request["action"], "select_deck_card")

    def test_runtime_records_duration_and_token_usage(self) -> None:
        client = DummyClient(
            [
                combat_payload(
                    actions=["end_turn"],
                    hand=[],
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(
                client=client,
                router=SinglePolicyRouter(MeteredFakeLLMPolicy('{"action":"end_turn","reason":"done"}')),
                config=RuntimeConfig(max_steps=1, output_dir=Path(tmp)),
            )
            summary = runtime.run()

        self.assertGreaterEqual(summary.duration_seconds, 0)
        self.assertEqual(summary.token_usage["prompt_tokens"], 10)
        self.assertEqual(summary.token_usage["completion_tokens"], 4)
        self.assertEqual(summary.token_usage["total_tokens"], 14)
        self.assertEqual(runtime.records[0].metrics["llm"]["model"], "fake-model")
        self.assertIn("step_duration_seconds", runtime.records[0].metrics)
        self.assertRegex(runtime.records[0].state_hash_before, r"^[0-9a-f]{16}$")
        self.assertRegex(runtime.records[0].state_hash_after, r"^[0-9a-f]{16}$")
        self.assertTrue(runtime.records[0].segment_id.startswith("seg_"))

    def test_continue_run_starts_retry_segment(self) -> None:
        main_menu = state_payload(screen="MAIN_MENU", actions=["continue_run"], run=None)
        combat = combat_payload(actions=["end_turn"], hand=[])

        class ContinuePolicy:
            def decide(self, state: GameStateSnapshot, knowledge: Any) -> PolicyDecision:
                return PolicyDecision.action_decision(AgentAction("continue_run"), reason="resume")

        client = DummyClient([main_menu, combat])
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(
                client=client,
                router=SinglePolicyRouter(ContinuePolicy()),
                config=RuntimeConfig(max_steps=1, output_dir=Path(tmp)),
            )
            summary = runtime.run()

        self.assertEqual(summary.segment_count, 2)
        self.assertEqual(runtime.segments[1].start_reason, "retry_from_checkpoint")
        self.assertEqual(runtime.segments[1].parent_segment_id, runtime.segments[0].segment_id)

    def test_runtime_executes_combat_action_plan_sequentially(self) -> None:
        first = combat_payload(
            actions=["play_card", "end_turn"],
            hand=[{"index": 0, "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
        )
        second = combat_payload(actions=["end_turn"], hand=[])
        third = combat_payload(actions=["play_card", "end_turn"], hand=[])

        class PlanPolicy:
            def decide(self, state: GameStateSnapshot, knowledge: Any) -> PolicyDecision:
                return PolicyDecision.action_plan_decision(
                    [
                        AgentAction("play_card", card_index=0, target_index=0),
                        AgentAction("end_turn"),
                    ],
                    reason="play a short combat plan",
                )

        client = DummyClient([first, second, third])
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(
                client=client,
                router=SinglePolicyRouter(PlanPolicy()),
                config=RuntimeConfig(max_steps=1, output_dir=Path(tmp), wait_timeout_seconds=1.0),
            )
            runtime.run()

        self.assertEqual([action.action for action in client.actions], ["play_card", "end_turn"])
        self.assertEqual(len(runtime.records[0].action_request["action_plan"]), 2)
        self.assertEqual(len(runtime.records[0].action_result["action_results"]), 2)

    def test_runtime_stops_action_plan_when_next_action_is_stale(self) -> None:
        first = combat_payload(
            actions=["play_card", "end_turn"],
            hand=[{"index": 0, "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
        )
        second = combat_payload(actions=["end_turn"], hand=[])

        class StalePlanPolicy:
            def decide(self, state: GameStateSnapshot, knowledge: Any) -> PolicyDecision:
                return PolicyDecision.action_plan_decision(
                    [
                        AgentAction("play_card", card_index=0, target_index=0),
                        AgentAction("play_card", card_index=1, target_index=0),
                    ],
                    reason="second action becomes stale",
                )

        client = DummyClient([first, second])
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(
                client=client,
                router=SinglePolicyRouter(StalePlanPolicy()),
                config=RuntimeConfig(max_steps=1, output_dir=Path(tmp), wait_timeout_seconds=1.0),
            )
            summary = runtime.run()

        self.assertEqual([action.action for action in client.actions], ["play_card"])
        self.assertEqual(summary.error_count, 0)
        self.assertEqual(runtime.records[0].decision["metadata"]["plan_stop_reason"], "validation_stopped:unavailable_action")

    def test_runtime_relocates_planned_card_by_instance_id(self) -> None:
        first = combat_payload(
            actions=["play_card", "end_turn"],
            hand=[
                {"index": 0, "card_instance_id": "card_a", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]},
                {"index": 1, "card_instance_id": "card_b", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]},
            ],
        )
        second = combat_payload(
            actions=["play_card", "end_turn"],
            hand=[{"index": 0, "card_instance_id": "card_b", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
        )
        third = combat_payload(actions=["end_turn"], hand=[])

        class StablePlanPolicy:
            def decide(self, state: GameStateSnapshot, knowledge: Any) -> PolicyDecision:
                return PolicyDecision.action_plan_decision(
                    [
                        AgentAction("play_card", card_instance_id="card_a", target_instance_id="enemy_1"),
                        AgentAction("play_card", card_instance_id="card_b", target_instance_id="enemy_1"),
                    ],
                    reason="execute two specific card instances",
                )

        client = DummyClient([first, second, third])
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(
                client=client,
                router=SinglePolicyRouter(StablePlanPolicy()),
                config=RuntimeConfig(max_steps=1, output_dir=Path(tmp), wait_timeout_seconds=1.0),
            )
            runtime.run()

        self.assertEqual([action.card_instance_id for action in client.actions], ["card_a", "card_b"])
        self.assertEqual([action.card_index for action in client.actions], [0, 0])


if __name__ == "__main__":
    unittest.main()
