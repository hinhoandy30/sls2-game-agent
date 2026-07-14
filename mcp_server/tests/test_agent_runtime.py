from __future__ import annotations

import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from sts2_agent_runtime.client import GameClientError, HttpGameClient, is_actionable_state
from sts2_agent_runtime.cli import _load_env_file, _port_from_base_url, enable_instant_mode, set_seed_for_new_run
from sts2_agent_runtime.contracts import ActionResult, AgentAction, GameStateSnapshot, KnowledgeContext, PolicyDecision
from sts2_agent_runtime.agent_context import ExperienceEvidence, ExperienceLesson, ExperienceScope, RunContextStore
from sts2_agent_runtime.experience import ExperienceRepository
from sts2_agent_runtime.knowledge import KnowledgeProvider
from sts2_agent_runtime.action_spec import action_spec_prompt_options, parse_llm_action_payload, parse_llm_action_plan_payload
from sts2_agent_runtime.legal_actions import build_legal_actions
from sts2_agent_runtime.llm import OpenAICompatiblePolicy
from sts2_agent_runtime.orchestration import AgentOrchestrator, CombatAgent, RouteStrategyAgent, RunDevelopmentAgent
from sts2_agent_runtime.review import ReviewReport, ReviewResult
from sts2_agent_runtime.runtime import AgentRuntime, RuntimeConfig, ValidationError, _state_summary
from sts2_agent_runtime.policies import EventPolicy, MapPolicy
from sts2_agent_runtime.strategy import StrategyProvider
from sts2_agent_runtime.summarize_run import render_markdown, summarize_run_dir
from sts2_agent_runtime.validate_knowledge import validate_knowledge_root


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


class DisabledConsoleClient:
    def run_console_command(self, command: str) -> ActionResult:
        raise GameClientError(
            "invalid_action",
            "run_console_command is disabled. Set STS2_ENABLE_DEBUG_ACTIONS=1 for development use.",
            retryable=False,
        )


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


class FakeRouteAgent(RouteStrategyAgent):
    def __init__(self, context_store: RunContextStore, response: str) -> None:
        super().__init__(context_store, api_key="test-key")
        self.response = response
        self.last_prompt: dict[str, Any] = {}

    def _chat(self, prompt: dict[str, Any]) -> str:
        self.last_prompt = prompt
        self.last_call_metadata = {"provider": "test", "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        return self.response


class FakeReviewAgent:
    def review(self, run_dir: Path, summary: Any) -> ReviewResult:
        lesson = ExperienceLesson(
            lesson_id="lesson_fixture_loss_v1",
            scope=ExperienceScope(screens=["SHOP"]),
            recommendation_zh="优先比较关键生存资源。",
            rationale_zh="fixture evidence",
            counterexamples_zh=["拥有充分防御时可删除牌。"],
            evidence=ExperienceEvidence(run_id=summary.run_id, segment_id="seg_fixture", step_indices=[0]),
            confidence=0.5,
        )
        return ReviewResult(
            report=ReviewReport(run_id=summary.run_id, outcome_zh="fixture loss", lessons=[lesson]),
            llm_metadata={"usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}},
        )


class AgentRuntimeTests(unittest.TestCase):
    def test_experience_repository_retrieves_scoped_historical_advice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = ExperienceRepository(Path(tmp))
            repository.save_lessons(
                [
                    ExperienceLesson(
                        lesson_id="lesson_map_skill_v1",
                        status="active",
                        scope=ExperienceScope(screens=["MAP"], deck_tags_any=["type:skill"]),
                        recommendation_zh="保留生命值。",
                        rationale_zh="过去对局的可追溯经验。",
                        evidence=ExperienceEvidence(run_id="older_run", step_indices=[8]),
                        confidence=0.8,
                    )
                ]
            )
            snapshot = GameStateSnapshot.from_raw(
                state_payload(
                    screen="MAP",
                    actions=["choose_map_node"],
                    run={"floor": 2, "deck": [{"card_id": "DEFEND", "card_type": "Skill"}], "potions": []},
                ),
                source="test",
            )
            context_store = RunContextStore(repository)

            packet = context_store.prompt_context(snapshot, "route_strategy")

        lessons = packet["historical_experience"]["lessons"]
        self.assertEqual(packet["historical_experience"]["lesson_ids"], ["lesson_map_skill_v1"])
        self.assertIn("历史复盘经验", lessons[0]["notice_zh"])

    def test_route_agent_uses_run_context_and_applies_valid_strategy_update(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="MAP",
                actions=["choose_map_node"],
                run={"floor": 2, "deck": [{"card_id": "DEFEND", "card_type": "Skill"}], "potions": []},
            ),
            source="test",
        )
        snapshot.state["map"] = {"available_nodes": [{"index": 3, "node_type": "Monster"}]}
        legal_id = build_legal_actions(snapshot)[0]["id"]
        context_store = RunContextStore()
        policy = FakeRouteAgent(
            context_store,
            '{"legal_action_id":"' + legal_id + '","reason":"route","strategy_update":{"risk_budget":"low","path_preferences":["Monster"]}}',
        )

        decision = policy.decide(snapshot, KnowledgeContext())

        self.assertEqual(decision.action.action, "choose_map_node")
        self.assertEqual(decision.metadata["agent"]["name"], "route_strategy")
        self.assertTrue(decision.metadata["agent"]["strategy_update"]["applied"])
        self.assertEqual(context_store.strategic_plan.risk_budget, "low")
        self.assertEqual(len(policy.last_prompt["messages"]), 5)
        self.assertIn('"packet":"run_context.v1"', policy.last_prompt["messages"][2]["content"])

    def test_route_agent_prompt_contains_grouped_remaining_map_routes(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="MAP",
                actions=["choose_map_node"],
                run={"floor": 2, "deck": [], "potions": []},
            ),
            source="test",
        )
        snapshot.state["map"] = {
            "current_node": {"row": 1, "col": 3},
            "map_generation_count": 1,
            "available_nodes": [
                {"index": 0, "node_id": "2:2", "row": 2, "col": 2, "node_type": "Monster", "state": "Travelable"},
                {"index": 1, "node_id": "2:4", "row": 2, "col": 4, "node_type": "Event", "state": "Travelable"},
            ],
            "nodes": [
                {"node_id": "0:3", "row": 0, "col": 3, "node_type": "Start", "visited": True, "child_node_ids": ["1:3"]},
                {"node_id": "1:3", "row": 1, "col": 3, "node_type": "Monster", "visited": True, "is_current": True, "child_node_ids": ["2:2", "2:4"]},
                {"node_id": "2:2", "row": 2, "col": 2, "node_type": "Monster", "child_node_ids": ["3:2"]},
                {"node_id": "2:4", "row": 2, "col": 4, "node_type": "Event", "child_node_ids": ["3:4"]},
                {"node_id": "3:2", "row": 3, "col": 2, "node_type": "Rest", "child_node_ids": ["4:3"]},
                {"node_id": "3:4", "row": 3, "col": 4, "node_type": "Elite", "child_node_ids": ["4:3"]},
                {"node_id": "4:3", "row": 4, "col": 3, "node_type": "Boss", "is_boss": True, "child_node_ids": []},
            ],
        }
        first_legal_id = build_legal_actions(snapshot)[0]["id"]
        policy = FakeRouteAgent(RunContextStore(), f'{{"legal_action_id":"{first_legal_id}","reason":"route"}}')

        policy.decide(snapshot, KnowledgeContext())

        route_planning = policy.last_prompt["state"]["route_planning"]
        self.assertEqual(route_planning["current_node_id"], "1:3")
        self.assertEqual(route_planning["route_count"], 2)
        self.assertEqual(route_planning["routes_omitted"], 0)
        self.assertNotIn("route_candidates", route_planning)
        self.assertNotIn("nodes", policy.last_prompt["state"]["map"])
        first_group = route_planning["route_groups"][0]
        self.assertEqual(first_group["next_node_id"], "2:2")
        self.assertEqual(first_group["next_legal_action_id"], first_legal_id)
        self.assertEqual(first_group["count_ranges"]["monster"], {"min": 1, "max": 1, "values": [1]})
        self.assertEqual(first_group["count_ranges"]["rest"], {"min": 1, "max": 1, "values": [1]})
        self.assertEqual(first_group["count_ranges"]["elite"], {"min": 0, "max": 0, "values": [0]})
        self.assertEqual(first_group["representative_routes"][0]["remaining_sequence"], ["Monster", "Rest", "Boss"])
        self.assertEqual([node["node_id"] for node in route_planning["visited_prefix"]], ["0:3"])

    def test_state_summary_logs_map_route_candidates(self) -> None:
        raw = state_payload(screen="MAP", actions=["choose_map_node"], run={"floor": 2, "potions": []})["data"]
        raw["map"] = {
            "current_node": {"row": 1, "col": 3},
            "map_generation_count": 1,
            "available_nodes": [
                {"index": 0, "node_id": "2:2", "row": 2, "col": 2, "node_type": "Monster", "state": "Travelable"},
            ],
            "nodes": [
                {"node_id": "1:3", "row": 1, "col": 3, "node_type": "Monster", "visited": True, "is_current": True, "child_node_ids": ["2:2"]},
                {"node_id": "2:2", "row": 2, "col": 2, "node_type": "Monster", "child_node_ids": ["3:2"]},
                {"node_id": "3:2", "row": 3, "col": 2, "node_type": "Boss", "is_boss": True, "child_node_ids": []},
            ],
        }

        summary = _state_summary(raw)

        self.assertEqual(summary["route_planning"]["route_count"], 1)
        self.assertEqual(summary["route_planning"]["route_groups"][0]["next_node_id"], "2:2")
        candidate = summary["route_planning"]["route_candidates"][0]
        self.assertEqual(candidate["next_legal_action_id"], "choose_map_node_option_0_2-2")
        self.assertEqual(candidate["remaining_sequence"], ["Monster", "Boss"])

    def test_agent_orchestrator_routes_gameplay_screens_without_llm_router_call(self) -> None:
        orchestrator = AgentOrchestrator(context_store=RunContextStore(), api_key="test-key")
        map_state = GameStateSnapshot.from_raw(state_payload(screen="MAP", actions=["choose_map_node"], run={"deck": [], "potions": []}), source="test")
        combat_state = GameStateSnapshot.from_raw(combat_payload(actions=["end_turn"], hand=[]), source="test")
        reward_state = GameStateSnapshot.from_raw(state_payload(screen="REWARD", actions=["proceed"], run={"deck": [], "potions": []}), source="test")

        self.assertIsInstance(orchestrator.select(map_state), RouteStrategyAgent)
        self.assertIsInstance(orchestrator.select(combat_state), CombatAgent)
        self.assertIsInstance(orchestrator.select(reward_state), RunDevelopmentAgent)

    def test_specialist_strategies_are_loaded_from_versioned_data_and_recorded(self) -> None:
        provider = StrategyProvider()
        combat_strategy = provider.get("combat")
        self.assertEqual(combat_strategy.strategy_id, "combat.baseline.v1")
        self.assertIn("信息边界", combat_strategy.render_instruction())

        orchestrator = AgentOrchestrator(context_store=RunContextStore(), api_key="test-key", strategy_provider=provider)
        state = GameStateSnapshot.from_raw(combat_payload(actions=["end_turn"], hand=[]), source="test")
        metadata = orchestrator.combat_agent.metadata_provider(state)

        self.assertEqual(metadata["strategy"]["strategy_id"], "combat.baseline.v1")
        self.assertEqual(metadata["strategy"]["strategy_revision"], 2)
        self.assertRegex(metadata["strategy"]["strategy_hash"], r"^[0-9a-f]{16}$")

    def test_summarize_run_extracts_human_timeline_and_route_groups(self) -> None:
        map_state = state_payload(screen="MAP", actions=["choose_map_node"], run={"floor": 1, "current_hp": 70, "potions": []})["data"]
        map_state["map"] = {
            "current_node": {"row": 0, "col": 3},
            "map_generation_count": 1,
            "available_nodes": [
                {"index": 0, "node_id": "1:2", "row": 1, "col": 2, "node_type": "Monster", "state": "Travelable"},
                {"index": 1, "node_id": "1:4", "row": 1, "col": 4, "node_type": "Shop", "state": "Travelable"},
            ],
            "nodes": [
                {"node_id": "0:3", "row": 0, "col": 3, "node_type": "Ancient", "visited": True, "is_current": True, "child_node_ids": ["1:2", "1:4"]},
                {"node_id": "1:2", "row": 1, "col": 2, "node_type": "Monster", "child_node_ids": ["2:2"]},
                {"node_id": "1:4", "row": 1, "col": 4, "node_type": "Shop", "child_node_ids": ["2:4"]},
                {"node_id": "2:2", "row": 2, "col": 2, "node_type": "Boss", "is_boss": True, "child_node_ids": []},
                {"node_id": "2:4", "row": 2, "col": 4, "node_type": "Boss", "is_boss": True, "child_node_ids": []},
            ],
        }
        map_summary = _state_summary(map_state)
        rows = [
            {
                "schema_version": "mvp0.v1",
                "run_id": "run_test",
                "segment_id": "seg",
                "step_index": 0,
                "observed_at": "now",
                "screen_before": "EVENT",
                "state_hash_before": "a",
                "state_hash_after": "b",
                "state_summary": {"screen": "EVENT", "floor": 1, "player_hp": 70},
                "knowledge_refs": [],
                "decision": {"type": "action", "reason": "proceed"},
                "action_request": {"action": "choose_event_option", "legal_action_id": "choose_event_option_option_0"},
                "action_result": {"ok": True, "action": "choose_event_option", "status": "completed", "stable": True, "message": "ok", "state": map_state},
            },
            {
                "schema_version": "mvp0.v1",
                "run_id": "run_test",
                "segment_id": "seg",
                "step_index": 1,
                "observed_at": "now",
                "screen_before": "MAP",
                "state_hash_before": "b",
                "state_hash_after": "c",
                "state_summary": map_summary,
                "knowledge_refs": [],
                "decision": {
                    "type": "action",
                    "reason": "choose shop branch",
                    "metadata": {
                        "agent": {"name": "route_strategy"},
                        "llm": {"model": "fake", "duration_seconds": 1.5, "usage": {"prompt_tokens": 100, "total_tokens": 120}},
                    },
                },
                "action_request": {"action": "choose_map_node", "legal_action_id": "choose_map_node_option_1_1-4"},
                "action_result": None,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "trajectory.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

            summary = summarize_run_dir(run_dir)
            markdown = render_markdown(summary)

        self.assertEqual(summary["token_totals"]["total_tokens"], 120)
        route_groups = summary["decisions"][1]["route_groups"]
        self.assertEqual({group["next_node_id"] for group in route_groups}, {"1:2", "1:4"})
        self.assertIn("choose shop branch", markdown)
        self.assertIn("Route groups", markdown)

    def test_summarize_run_infers_seed_and_recovers_bundle_options(self) -> None:
        bundle_state = state_payload(
            screen="BUNDLE_SELECTION",
            actions=["choose_bundle"],
            run={"floor": 1, "current_hp": 64},
        )["data"]
        bundle_state["run_id"] = "SEED123"
        bundle_state["bundles"] = [
            {
                "index": 0,
                "cards": [
                    {"index": 0, "card_id": "ANGER", "name": "愤怒", "energy_cost": 0, "resolved_rules_text": "造成6点伤害。"},
                    {"index": 1, "card_id": "CINDER", "name": "余烬", "energy_cost": 2, "resolved_rules_text": "造成18点伤害。"},
                ],
            },
            {
                "index": 1,
                "cards": [
                    {"index": 0, "card_id": "BODY_SLAM", "name": "全身撞击", "energy_cost": 1, "resolved_rules_text": "造成你当前格挡值的伤害。"},
                ],
            },
        ]
        rows = [
            {
                "schema_version": "mvp0.v1",
                "run_id": "run_unknown",
                "segment_id": "seg",
                "step_index": 0,
                "observed_at": "now",
                "screen_before": "EVENT",
                "state_summary": {"screen": "EVENT", "floor": 1, "player_hp": 64},
                "decision": {"type": "action", "reason": "choose bundle event"},
                "action_request": {"action": "choose_event_option", "legal_action_id": "choose_event_option_option_1"},
                "action_result": {"ok": True, "state": bundle_state},
            },
            {
                "schema_version": "mvp0.v1",
                "run_id": "run_unknown",
                "segment_id": "seg",
                "step_index": 1,
                "observed_at": "now",
                "screen_before": "BUNDLE_SELECTION",
                "state_summary": {
                    "screen": "BUNDLE_SELECTION",
                    "floor": 1,
                    "player_hp": 64,
                    "legal_action_ids": ["choose_bundle_option_0", "choose_bundle_option_1"],
                },
                "decision": {"type": "action", "reason": "pick bundle"},
                "action_request": {"action": "choose_bundle", "legal_action_id": "choose_bundle_option_0"},
                "action_result": None,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "trajectory.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

            summary = summarize_run_dir(run_dir)
            markdown = render_markdown(summary)

        self.assertEqual(summary["seed"], "SEED123")
        self.assertEqual(summary["run_id"], "SEED123")
        self.assertEqual(len(summary["decisions"][1]["bundles"]), 2)
        self.assertIn("Seed: `SEED123`", markdown)
        self.assertIn("愤怒", markdown)
        self.assertIn("全身撞击", markdown)

    def test_runtime_writes_review_and_experience_after_game_over(self) -> None:
        game_over = state_payload(screen="GAME_OVER", actions=[], run={"floor": 7, "deck": [], "potions": []})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = ExperienceRepository(root / "experience")
            runtime = AgentRuntime(
                client=DummyClient([game_over]),
                config=RuntimeConfig(max_steps=1, output_dir=root / "runs"),
                router=AgentOrchestrator(context_store=RunContextStore(repository), api_key="test-key"),
                review_agent=FakeReviewAgent(),
                experience_repository=repository,
            )
            summary = runtime.run()

            run_dir = next((root / "runs").iterdir())
            lessons = list((root / "experience" / "lessons").glob("*.json"))
            review_exists = (run_dir / "review.json").is_file()
            context_exists = (run_dir / "context.jsonl").is_file()

        self.assertEqual(summary.result, "loss")
        self.assertEqual(summary.review_path, "review.json")
        self.assertEqual(summary.experience_lesson_count, 1)
        self.assertEqual(summary.token_usage["total_tokens"], 10)
        self.assertTrue(review_exists)
        self.assertTrue(context_exists)
        self.assertEqual(len(lessons), 1)

    def test_knowledge_provider_loads_current_monsters_from_chinese_json(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="COMBAT",
                actions=["end_turn"],
                combat={
                    "enemies": [
                        {"enemy_id": "NIBBIT"},
                        {"enemy_id": "LEAF_SLIME_S"},
                        {"enemy_id": "LEAF_SLIME_M"},
                        {"enemy_id": "TWIG_SLIME_S"},
                        {"enemy_id": "TWIG_SLIME_M"},
                        {"enemy_id": "SHRINKER_BEETLE"},
                        {"enemy_id": "FUZZY_WURM_CRAWLER"},
                        {"enemy_id": "UNKNOWN_MONSTER"},
                    ],
                    "hand": [],
                },
                run={"floor": 1, "potions": []},
            ),
            source="test",
        )

        knowledge = KnowledgeProvider().for_state(snapshot)

        self.assertEqual(
            knowledge.refs,
            [
                "monster:FUZZY_WURM_CRAWLER",
                "monster:LEAF_SLIME_M",
                "monster:LEAF_SLIME_S",
                "monster:NIBBIT",
                "monster:SHRINKER_BEETLE",
                "monster:TWIG_SLIME_M",
                "monster:TWIG_SLIME_S",
                "monster:UNKNOWN_MONSTER",
            ],
        )
        self.assertEqual(
            [entry["enemy_id"] for entry in knowledge.monsters],
            [
                "NIBBIT",
                "LEAF_SLIME_S",
                "LEAF_SLIME_M",
                "TWIG_SLIME_S",
                "TWIG_SLIME_M",
                "SHRINKER_BEETLE",
                "FUZZY_WURM_CRAWLER",
            ],
        )
        self.assertEqual(knowledge.monsters[0]["name_zh"], "尼比特")
        self.assertIn("wiki:sts2-nibbit", knowledge.monsters[0]["source_refs"])
        self.assertTrue(any(source["ref"] == "wiki:sts2-nibbit" for source in knowledge.sources))
        self.assertTrue(all(source["knowledge_path"] == "monsters/NIBBIT.json" for source in knowledge.sources if source["ref"] == "wiki:sts2-nibbit"))

    def test_knowledge_provider_loads_event_entry_from_state_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events_dir = root / "events"
            events_dir.mkdir()
            (events_dir / "TEST_EVENT.json").write_text(
                json.dumps(
                    {
                        "schema_version": "sts2-event-knowledge.v1",
                        "kind": "event",
                        "event_id": "TEST_EVENT",
                        "name_zh": "测试事件",
                        "act_ids": ["OVERGROWTH"],
                        "summary_zh": "用于验证事件知识按 ID 加载。",
                        "flow_facts_zh": ["第二页仍可能出现选项。"],
                        "sources": [
                            {
                                "ref": "test:event",
                                "title_zh": "测试来源",
                                "url": "https://example.test/event",
                                "retrieved_at": "2026-07-13",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshot = GameStateSnapshot.from_raw(
                state_payload(screen="EVENT", actions=["choose_event_option"], run={"floor": 1, "potions": []}),
                source="test",
            )
            snapshot.state["event"] = {"event_id": "TEST_EVENT"}

            knowledge = KnowledgeProvider(root_dir=root).for_state(snapshot)

        self.assertEqual(knowledge.refs, ["event:TEST_EVENT"])
        self.assertEqual(knowledge.events[0]["name_zh"], "测试事件")
        self.assertEqual(knowledge.sources[0]["ref"], "test:event")
        self.assertEqual(knowledge.sources[0]["knowledge_path"], "events/TEST_EVENT.json")

    def test_knowledge_provider_loads_card_entry_from_hand_card_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cards_dir = root / "cards"
            cards_dir.mkdir()
            (cards_dir / "BATTLE_TRANCE.json").write_text(
                json.dumps(
                    {
                        "schema_version": "sts2-card-knowledge.v1",
                        "kind": "card",
                        "card_id": "BATTLE_TRANCE",
                        "name_zh": "战斗专注",
                        "character_ids": ["IRONCLAD"],
                        "card_type": "Skill",
                        "rarity": "Uncommon",
                        "cost_zh": "0 能量",
                        "summary_zh": "抽牌技能。",
                        "mechanics_zh": ["抽 3 张牌。", "本回合不能再抽牌。"],
                        "tags": ["过牌", "0费"],
                        "upgrade": {"summary_zh": "抽更多牌。", "changes_zh": ["抽牌数量增加。"]},
                        "sources": [{"ref": "test:card", "title_zh": "测试来源", "url": "https://example.com/card", "retrieved_at": "2026-07-14"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshot = GameStateSnapshot.from_raw(
                combat_payload(
                    actions=["end_turn"],
                    hand=[{"index": 0, "card_id": "BATTLE_TRANCE", "playable": True, "requires_target": False}],
                ),
                source="test",
            )

            knowledge = KnowledgeProvider(root_dir=root).for_state(snapshot)

        self.assertEqual(knowledge.refs, ["card:BATTLE_TRANCE", "monster:TEST_ENEMY"])
        self.assertEqual(knowledge.cards[0]["card_id"], "BATTLE_TRANCE")
        self.assertEqual(knowledge.cards[0]["name_zh"], "战斗专注")
        self.assertEqual(knowledge.sources[0]["knowledge_path"], "cards/BATTLE_TRANCE.json")

    def test_validate_knowledge_root_reports_filename_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "monsters").mkdir(parents=True)
            (root / "events").mkdir()
            (root / "cards").mkdir()
            (root / "strategy" / "card_priorities").mkdir(parents=True)
            (root / "monsters" / "WRONG_ID.json").write_text(
                json.dumps(
                    {
                        "schema_version": "sts2-monster-knowledge.v1",
                        "kind": "monster",
                        "enemy_id": "NIBBIT",
                        "name_zh": "尼比",
                        "act_ids": ["OVERGROWTH"],
                        "encounter_pool_zh": "测试",
                        "summary_zh": "测试",
                        "pattern_zh": "测试",
                        "moves": [{"name_zh": "攻击", "effect_zh": "造成伤害"}],
                        "risk_facts_zh": [],
                        "sources": [{"ref": "test", "title_zh": "测试", "url": "https://example.com", "retrieved_at": "2026-07-14"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            errors = validate_knowledge_root(root)

        self.assertTrue(any("filename must match enemy_id" in error for error in errors))

    def test_validate_knowledge_root_accepts_card_priority_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "monsters").mkdir(parents=True)
            (root / "events").mkdir()
            (root / "cards").mkdir()
            priorities_dir = root / "strategy" / "card_priorities"
            priorities_dir.mkdir(parents=True)
            (priorities_dir / "BATTLE_TRANCE.json").write_text(
                json.dumps(
                    {
                        "schema_version": "sts2-card-priority-strategy.v1",
                        "kind": "card_priority",
                        "strategy_id": "card-priority.BATTLE_TRANCE.v1",
                        "card_id": "BATTLE_TRANCE",
                        "name_zh": "战斗专注",
                        "character_ids": ["IRONCLAD"],
                        "baseline_priority": "high",
                        "role_tags": ["过牌", "0费"],
                        "good_when_zh": ["牌组缺过牌。"],
                        "bad_when_zh": ["本回合后续依赖继续抽牌。"],
                        "pick_vs_skip_zh": ["缺过牌时优先级较高。"],
                        "upgrade_priority_zh": "中等。",
                        "notes_zh": ["条件化优先级。"],
                        "sources": [{"ref": "test:priority", "title_zh": "测试来源", "url": "https://example.com/priority", "retrieved_at": "2026-07-14"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            errors = validate_knowledge_root(root)

        self.assertEqual(errors, [])

    def test_llm_prompt_contains_compact_knowledge_entries(self) -> None:
        snapshot = GameStateSnapshot.from_raw(combat_payload(actions=["end_turn"], hand=[]), source="test")
        knowledge = KnowledgeContext(
            refs=["monster:NIBBIT"],
            monsters=[{"enemy_id": "NIBBIT", "name_zh": "尼比特", "summary_zh": "固定循环。"}],
        )

        policy = FakeLLMPolicy('{"action":"end_turn","reason":"done"}')
        policy.decide(snapshot, knowledge=knowledge)

        self.assertEqual(policy.last_prompt["knowledge"]["monsters"][0]["name_zh"], "尼比特")
        self.assertEqual(policy.last_prompt["knowledge"]["refs"], ["monster:NIBBIT"])

    def test_llm_prompt_keeps_knowledge_before_dynamic_state_and_reports_hash(self) -> None:
        snapshot = GameStateSnapshot.from_raw(combat_payload(actions=["end_turn"], hand=[]), source="test")
        knowledge = KnowledgeContext(
            refs=["monster:NIBBIT", "monster:SHRINKER_BEETLE"],
            monsters=[
                {"enemy_id": "SHRINKER_BEETLE", "name_zh": "缩小甲虫"},
                {"enemy_id": "NIBBIT", "name_zh": "尼比特"},
            ],
        )
        policy = FakeLLMPolicy('{"action":"end_turn","reason":"done"}')

        policy.decide(snapshot, knowledge=knowledge)

        messages = policy.last_prompt["messages"]
        self.assertEqual([message["role"] for message in messages], ["system", "user", "user", "user"])
        self.assertIn('"packet":"knowledge_packet.v1"', messages[2]["content"])
        self.assertIn('"enemy_id":"NIBBIT"', messages[2]["content"])
        self.assertLess(messages[2]["content"].index("NIBBIT"), messages[2]["content"].index("SHRINKER_BEETLE"))
        self.assertIn('"packet":"decision_state.v1"', messages[3]["content"])
        metadata = policy.last_prompt["prompt_metadata"]
        self.assertRegex(metadata["knowledge_packet_hash"], r"^[0-9a-f]{16}$")
        self.assertGreater(metadata["message_characters"]["decision_state"], 0)

    def test_equivalent_knowledge_has_the_same_packet_hash_despite_input_order(self) -> None:
        snapshot = GameStateSnapshot.from_raw(combat_payload(actions=["end_turn"], hand=[]), source="test")
        first = FakeLLMPolicy('{"action":"end_turn","reason":"done"}')
        second = FakeLLMPolicy('{"action":"end_turn","reason":"done"}')
        first.decide(
            snapshot,
            knowledge=KnowledgeContext(
                refs=["monster:NIBBIT", "monster:SHRINKER_BEETLE"],
                monsters=[{"enemy_id": "NIBBIT"}, {"enemy_id": "SHRINKER_BEETLE"}],
            ),
        )
        second.decide(
            snapshot,
            knowledge=KnowledgeContext(
                refs=["monster:SHRINKER_BEETLE", "monster:NIBBIT"],
                monsters=[{"enemy_id": "SHRINKER_BEETLE"}, {"enemy_id": "NIBBIT"}],
            ),
        )

        self.assertEqual(
            first.last_prompt["prompt_metadata"]["knowledge_packet_hash"],
            second.last_prompt["prompt_metadata"]["knowledge_packet_hash"],
        )

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

    def test_legal_actions_include_bundle_options(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(screen="BUNDLE_SELECTION", actions=["choose_bundle"], run={"deck": [], "potions": []}),
            source="test",
        )
        snapshot.state["bundles"] = [{"index": 0, "cards": []}, {"index": 1, "cards": []}]

        options = [item for item in build_legal_actions(snapshot) if item["action"] == "choose_bundle"]

        self.assertEqual([item["option_index"] for item in options], [0, 1])

    def test_action_spec_accepts_seed_payload(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(screen="CHARACTER_SELECT", actions=["set_seed"], run=None),
            source="test",
        )

        action = parse_llm_action_payload({"action": "set_seed", "seed": "V16VSX4954"}, snapshot)

        self.assertEqual(action.to_request()["seed"], "V16VSX4954")

    def test_seed_bootstrap_opens_character_select_and_verifies_echo(self) -> None:
        def character_select(seed: str | None = None) -> dict[str, Any]:
            payload = state_payload(screen="CHARACTER_SELECT", actions=["set_seed", "select_character"], run=None)
            payload["data"]["screen"] = "UNKNOWN"
            payload["data"]["character_select"] = {"seed": seed}
            return payload

        class SeedClient:
            def __init__(self) -> None:
                self.state = state_payload(screen="MAIN_MENU", actions=["open_character_select"], run=None)
                self.actions: list[AgentAction] = []
                self.pending_menu = True

            def get_state(self) -> dict[str, Any]:
                if self.pending_menu:
                    self.pending_menu = False
                    return state_payload(screen="MAIN_MENU", actions=[], run=None)
                return self.state

            def act(self, action: AgentAction) -> ActionResult:
                self.actions.append(action)
                if action.action == "open_character_select":
                    self.state = character_select()
                elif action.action == "set_seed":
                    self.state = character_select(action.payload["seed"])
                return ActionResult(ok=True, action=action.action, status="completed", stable=True, message="ok", state=self.state["data"])

            def wait_until_actionable(self, timeout_seconds: float) -> dict[str, Any]:
                return self.state

        client = SeedClient()

        state = set_seed_for_new_run(client, "V16VSX4954")

        self.assertEqual([action.action for action in client.actions], ["open_character_select", "set_seed"])
        self.assertEqual(client.actions[1].payload["seed"], "V16VSX4954")
        self.assertEqual(state["character_select"]["seed"], "V16VSX4954")

    def test_seed_bootstrap_replaces_existing_run_only_when_explicit(self) -> None:
        def character_select(seed: str | None = None) -> dict[str, Any]:
            payload = state_payload(screen="CHARACTER_SELECT", actions=["set_seed", "select_character"], run=None)
            payload["data"]["character_select"] = {"seed": seed}
            return payload

        class SeedClient:
            def __init__(self) -> None:
                self.state = state_payload(screen="MAIN_MENU", actions=["continue_run", "abandon_run"], run=None)
                self.actions: list[AgentAction] = []

            def get_state(self) -> dict[str, Any]:
                return self.state

            def act(self, action: AgentAction) -> ActionResult:
                self.actions.append(action)
                if action.action == "abandon_run":
                    self.state = state_payload(screen="MODAL", actions=["confirm_modal", "dismiss_modal"], run=None)
                elif action.action == "confirm_modal":
                    self.state = state_payload(screen="MAIN_MENU", actions=["open_character_select"], run=None)
                elif action.action == "open_character_select":
                    self.state = character_select()
                elif action.action == "set_seed":
                    self.state = character_select(action.payload["seed"])
                return ActionResult(ok=True, action=action.action, status="completed", stable=True, message="ok", state=self.state["data"])

        client = SeedClient()
        state = set_seed_for_new_run(client, "V16VSX4954", replace_existing_run=True)

        self.assertEqual([action.action for action in client.actions], ["abandon_run", "confirm_modal", "open_character_select", "set_seed"])
        self.assertEqual(state["character_select"]["seed"], "V16VSX4954")

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

    def test_targeted_potion_legal_action_carries_target_instance_id(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            state_payload(
                screen="COMBAT",
                actions=["use_potion", "end_turn"],
                run={
                    "floor": 1,
                    "current_hp": 70,
                    "potions": [
                        {
                            "index": 0,
                            "potion_id": "FIRE_POTION",
                            "name": "火焰药水",
                            "occupied": True,
                            "can_use": True,
                            "can_discard": True,
                            "requires_target": True,
                            "valid_target_indices": [0],
                        }
                    ],
                },
                combat={
                    "player": {"current_hp": 70, "energy": 3},
                    "hand": [],
                    "enemies": [{"index": 0, "enemy_instance_id": "enemy_1", "enemy_id": "TEST_ENEMY", "current_hp": 20, "is_alive": True}],
                },
                turn=1,
            ),
            source="test",
        )

        potion_action = next(item for item in build_legal_actions(snapshot) if item["action"] == "use_potion")

        self.assertEqual(potion_action["target_instance_id"], "enemy_1")
        self.assertIn("enemy-1", potion_action["id"])
        runtime = AgentRuntime(client=DummyClient([]))
        action = AgentAction("use_potion", potion_index=0, target_instance_id="enemy_1", legal_action_id=potion_action["id"])
        runtime.validate_action(snapshot, action)
        self.assertEqual(action.target_index, 0)

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

    def test_llm_repairs_empty_combat_action_plan(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card", "end_turn"],
                hand=[{"index": 0, "card_instance_id": "card_101", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )
        play_id = next(item["id"] for item in build_legal_actions(snapshot) if item["action"] == "play_card")
        policy = FakeLLMPolicy(
            [
                '{"type":"action","action_plan":{"actions":[]},"reason":"invalid empty plan"}',
                '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + play_id + '"}]},"reason":"repaired plan"}',
            ],
            enable_action_plan=True,
        )

        decision = policy.decide(snapshot, knowledge=KnowledgeContext())

        self.assertEqual([action.legal_action_id for action in decision.action_plan], [play_id])
        self.assertEqual(decision.reason, "repaired plan")

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

    def test_llm_stable_combat_plan_prompt_includes_usable_potions(self) -> None:
        payload = combat_payload(
            actions=["play_card", "use_potion", "discard_potion", "end_turn"],
            hand=[{"index": 0, "card_instance_id": "card_101", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
        )
        payload["data"]["run"]["potions"] = [
            {"index": 0, "potion_id": "POTION_OF_BINDING", "name": "缚魂药水", "occupied": True, "can_use": True, "can_discard": True, "requires_target": False}
        ]
        snapshot = GameStateSnapshot.from_raw(payload, source="test")
        potion_id = next(item["id"] for item in build_legal_actions(snapshot) if item["action"] == "use_potion")
        policy = FakeLLMPolicy(
            '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + potion_id + '"},{"legal_action_id":"end_turn"}]},"reason":"use potion"}',
            enable_action_plan=True,
        )

        decision = policy.decide(snapshot, knowledge=type("K", (), {"refs": []})())

        plan_actions = {item["action"] for item in policy.last_prompt["plan_legal_actions"]}
        self.assertIn("use_potion", plan_actions)
        self.assertIn(potion_id, {item["id"] for item in policy.last_prompt["plan_legal_actions"]})
        self.assertNotIn("discard_potion", plan_actions)
        self.assertEqual([action.action for action in decision.action_plan], ["use_potion", "end_turn"])

    def test_combat_agent_requires_and_records_short_combat_audit(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card", "end_turn"],
                hand=[{"index": 0, "card_instance_id": "card_a", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )
        play_id = next(item["id"] for item in build_legal_actions(snapshot) if item["action"] == "play_card")
        policy = FakeLLMPolicy(
            '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + play_id + '"},{"legal_action_id":"end_turn"}]},'
            '"combat_audit":{"primary_target_id":"enemy_1","lethal_this_turn":"no","defense_posture":"accept_damage_for_tempo",'
            '"risk_summary_zh":"当前无法稳定斩杀，保留节奏。","replan_after":[]},"reason":"short plan"}',
            enable_action_plan=True,
        )
        policy.agent_name = "combat"
        policy.agent_instruction = "combat protocol"

        decision = policy.decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertIn("combat_audit", decision.metadata)
        self.assertEqual(decision.metadata["combat_audit"]["primary_target_id"], "enemy_1")
        self.assertIn("combat_audit", policy.last_prompt["response_schema"])

    def test_combat_prompt_includes_live_combat_piles(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card", "end_turn"],
                hand=[{"index": 0, "card_instance_id": "card_a", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )
        snapshot.state["agent_view"]["run"] = {
            "piles": {
                "draw_cards": [{"card_id": "DEFEND"}],
                "discard_cards": [{"card_id": "BASH"}],
                "exhaust_cards": [],
            }
        }
        play_id = next(item["id"] for item in build_legal_actions(snapshot) if item["action"] == "play_card")
        policy = FakeLLMPolicy(
            '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + play_id + '"}]},'
            '"combat_audit":{"primary_target_id":"enemy_1","lethal_this_turn":"no","defense_posture":"unknown",'
            '"risk_summary_zh":"牌堆信息已纳入判断。","replan_after":[]}}',
            enable_action_plan=True,
        )
        policy.agent_name = "combat"
        policy.agent_instruction = "combat protocol"

        policy.decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(policy.last_prompt["state"]["combat_piles"]["draw_cards"], [{"card_id": "DEFEND"}])
        self.assertEqual(policy.last_prompt["state"]["combat_piles"]["discard_cards"], [{"card_id": "BASH"}])

    def test_combat_agent_repairs_audit_boundary_outside_plan(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card", "end_turn"],
                hand=[{"index": 0, "card_instance_id": "card_a", "card_id": "STRIKE", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )
        play_id = next(item["id"] for item in build_legal_actions(snapshot) if item["action"] == "play_card")
        policy = FakeLLMPolicy(
            [
                '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + play_id + '"}]},'
                '"combat_audit":{"primary_target_id":null,"lethal_this_turn":"unknown","defense_posture":"unknown",'
                '"risk_summary_zh":"需要重新确认。","replan_after":[{"legal_action_id":"missing","reason":"draw_cards"}]}}',
                '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + play_id + '"}]},'
                '"combat_audit":{"primary_target_id":null,"lethal_this_turn":"unknown","defense_posture":"unknown",'
                '"risk_summary_zh":"需要重新确认。","replan_after":[]}}',
            ],
            enable_action_plan=True,
        )
        policy.agent_name = "combat"
        policy.agent_instruction = "combat protocol"

        decision = policy.decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual(decision.metadata["combat_audit"]["replan_after"], [])

    def test_combat_agent_repairs_actions_after_declared_boundary(self) -> None:
        snapshot = GameStateSnapshot.from_raw(
            combat_payload(
                actions=["play_card", "end_turn"],
                hand=[{"index": 0, "card_instance_id": "card_a", "card_id": "DRAW_CARD", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
            ),
            source="test",
        )
        play_id = next(item["id"] for item in build_legal_actions(snapshot) if item["action"] == "play_card")
        audit = (
            '"combat_audit":{"primary_target_id":"enemy_1","lethal_this_turn":"unknown","defense_posture":"unknown",'
            '"risk_summary_zh":"抽牌后需要重规划。","replan_after":[{"legal_action_id":"' + play_id + '","reason":"draw_cards"}]}'
        )
        policy = FakeLLMPolicy(
            [
                '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + play_id + '"},{"legal_action_id":"end_turn"}]},' + audit + '}',
                '{"type":"action","action_plan":{"actions":[{"legal_action_id":"' + play_id + '"}]},' + audit + '}',
            ],
            enable_action_plan=True,
        )
        policy.agent_name = "combat"
        policy.agent_instruction = "combat protocol"

        decision = policy.decide(snapshot, knowledge=type("K", (), {"refs": []})())

        self.assertEqual([action.legal_action_id for action in decision.action_plan], [play_id])

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

    def test_enable_instant_mode_explains_debug_action_requirement(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "--launch-debug-session"):
            enable_instant_mode(DisabledConsoleClient(), "instant")

    def test_http_client_preserves_structured_http_error_payload(self) -> None:
        error_body = BytesIO(
            b'{"ok":false,"error":{"code":"invalid_action","message":"debug action disabled","retryable":false,"details":{"action":"run_console_command"}}}'
        )
        http_error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
            "http://127.0.0.1:8080/action",
            409,
            "Conflict",
            hdrs=None,
            fp=error_body,
        )
        with patch("sts2_agent_runtime.client.request.urlopen", side_effect=http_error):
            with self.assertRaises(GameClientError) as cm:
                HttpGameClient().run_console_command("instant")

        self.assertEqual(cm.exception.code, "invalid_action")
        self.assertEqual(cm.exception.details["action"], "run_console_command")

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

    def test_runtime_stops_action_plan_at_validated_tactical_boundary(self) -> None:
        first = combat_payload(
            actions=["play_card", "end_turn"],
            hand=[{"index": 0, "card_instance_id": "card_a", "card_id": "DRAW_CARD", "playable": True, "requires_target": True, "valid_target_indices": [0]}],
        )
        second = combat_payload(actions=["end_turn"], hand=[])

        class BoundaryPolicy:
            def decide(self, state: GameStateSnapshot, knowledge: Any) -> PolicyDecision:
                play_id = next(item["id"] for item in build_legal_actions(state) if item["action"] == "play_card")
                return PolicyDecision.action_plan_decision(
                    [
                        AgentAction("play_card", card_index=0, card_instance_id="card_a", target_index=0, target_instance_id="enemy_1", legal_action_id=play_id),
                        AgentAction("end_turn", legal_action_id="end_turn"),
                    ],
                    reason="play then redraw",
                    metadata={
                        "combat_audit": {
                            "replan_after": [{"legal_action_id": play_id, "reason": "draw_cards"}],
                        }
                    },
                )

        client = DummyClient([first, second])
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(
                client=client,
                router=SinglePolicyRouter(BoundaryPolicy()),
                config=RuntimeConfig(max_steps=1, output_dir=Path(tmp), wait_timeout_seconds=1.0),
            )
            runtime.run()

        self.assertEqual([action.action for action in client.actions], ["play_card"])
        self.assertEqual(runtime.records[0].decision["metadata"]["plan_stop_reason"], "tactical_replan:draw_cards")

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
