from __future__ import annotations

import argparse
import os
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlparse

from .contracts import AgentAction
from .client import GameClientError, HttpGameClient, action_names, unwrap_data
from .agent_context import RunContextStore
from .experience import ExperienceRepository
from .llm import GAMEPLAY_LLM_SCREENS, LLMScreenRouter, OpenAICompatiblePolicy
from .orchestration import AgentOrchestrator
from .review import RunReviewAgent
from .runtime import AgentRuntime, RuntimeConfig
from .strategy import StrategyProvider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MVP0 STS2 agent runtime.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output-dir", default="runs/agent-runtime")
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--wait-timeout", type=float, default=20.0)
    parser.add_argument("--launch-steam", action="store_true")
    parser.add_argument("--launch-debug-session", action="store_true")
    parser.add_argument("--steam-url", default="steam://run/2868840")
    parser.add_argument("--enable-instant", action="store_true")
    parser.add_argument("--instant-command", default="instant")
    parser.add_argument("--seed", help="Set a fixed seed before a new singleplayer run embarks.")
    parser.add_argument(
        "--replace-existing-run",
        action="store_true",
        help="Explicitly abandon an existing main-menu run before starting the seeded run.",
    )
    parser.add_argument("--resume", action="store_true", help="Connect to the current game state and continue from there.")
    parser.add_argument("--stop-after-first-combat", action="store_true")
    parser.add_argument("--stop-on-reward-after-combat", action="store_true")
    parser.add_argument("--policy", choices=["heuristic", "llm", "multi-agent"], default="heuristic")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-screens", choices=["gameplay", "all"], default="gameplay")
    parser.add_argument(
        "--llm-action-plan",
        dest="llm_action_plan",
        action="store_true",
        help="Compatibility flag; stable combat planning is enabled by default for the LLM policy.",
    )
    parser.add_argument(
        "--single-action",
        dest="llm_action_plan",
        action="store_false",
        help="Disable combat action plans and ask the LLM for one action at a time.",
    )
    parser.set_defaults(llm_action_plan=True)
    parser.add_argument("--max-plan-actions", type=int, default=5, help="Maximum actions to execute from one LLM combat plan.")
    parser.add_argument("--experience-dir", default="agent_knowledge/experience/v1", help="Directory for review-generated strategy experience.")
    parser.add_argument("--strategy-dir", default=None, help="Versioned specialist strategy directory; defaults to data/strategies/v1.")
    parser.add_argument("--no-review-on-game-over", action="store_true", help="Do not run the offline review agent after GAME_OVER.")
    parser.add_argument("--cleanup-only", action="store_true")
    parser.add_argument("--abandon-run", action="store_true")
    parser.add_argument("--shutdown-game", action="store_true")
    args = parser.parse_args(argv)
    if args.replace_existing_run and not args.seed:
        parser.error("--replace-existing-run is only valid together with --seed.")
    _load_env_files()

    if args.launch_debug_session:
        _launch_debug_session(args.base_url)
    elif args.launch_steam:
        subprocess.run(["open", args.steam_url], check=False)

    client = HttpGameClient(base_url=args.base_url)
    if args.launch_steam or args.launch_debug_session:
        _wait_for_health(client, timeout_seconds=120)
    if args.seed:
        set_seed_for_new_run(client, args.seed, replace_existing_run=args.replace_existing_run)
    if args.enable_instant:
        enable_instant_mode(client, args.instant_command)

    if args.cleanup_only:
        if args.abandon_run:
            abandon_current_run(client)
        if args.shutdown_game:
            shutdown_game_processes()
        return 0

    router = None
    review_agent = None
    experience_repository = None
    if args.policy == "llm":
        screens = None if args.llm_screens == "gameplay" else {
            "MAIN_MENU",
            "CHARACTER_SELECT",
            *GAMEPLAY_LLM_SCREENS,
            "GAME_OVER",
        }
        router = LLMScreenRouter(
            llm_policy=OpenAICompatiblePolicy(
                model=args.llm_model,
                enable_action_plan=args.llm_action_plan,
                max_plan_actions=args.max_plan_actions,
            ),
            llm_screens=screens,
        )
    elif args.policy == "multi-agent":
        experience_repository = ExperienceRepository(Path(args.experience_dir))
        context_store = RunContextStore(experience_repository)
        router = AgentOrchestrator(
            context_store=context_store,
            model=args.llm_model,
            enable_action_plan=args.llm_action_plan,
            max_plan_actions=args.max_plan_actions,
            strategy_provider=StrategyProvider(Path(args.strategy_dir)) if args.strategy_dir else None,
        )
        if not args.no_review_on_game_over:
            review_agent = RunReviewAgent(model=args.llm_model)

    runtime = AgentRuntime(
        client=client,
        config=RuntimeConfig(
            max_steps=args.max_steps,
            wait_timeout_seconds=args.wait_timeout,
            output_dir=Path(args.output_dir),
            stop_after_first_combat=args.stop_after_first_combat,
            stop_on_reward_after_combat=args.stop_on_reward_after_combat,
        ),
        router=router,
        review_agent=review_agent,
        experience_repository=experience_repository,
    )
    summary = runtime.run()
    print(summary.to_dict())
    if args.abandon_run:
        abandon_current_run(client)
    if args.shutdown_game:
        shutdown_game_processes()
    return 0


def _launch_debug_session(base_url: str) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "start-game-session.sh"
    port = _port_from_base_url(base_url)
    subprocess.run(
        [str(script), "--enable-debug-actions", "--api-port", str(port)],
        check=True,
        capture_output=True,
        text=True,
    )


def _port_from_base_url(base_url: str) -> int:
    parsed = urlparse(base_url)
    if parsed.port is not None:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def _wait_for_health(client: HttpGameClient, *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            client.health()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"Timed out waiting for STS2 health: {last_error}")


def set_seed_for_new_run(client: HttpGameClient, seed: str, *, replace_existing_run: bool = False) -> dict:
    """Navigate only as far as character select, then set and verify a reproducible run seed."""
    requested_seed = seed.strip()
    if not requested_seed or len(requested_seed) > 64:
        raise ValueError("--seed must contain 1 to 64 non-whitespace characters.")

    state = _wait_for_seed_screen(client)
    screen = _state_screen(state)
    replaced_run = False
    while screen == "MAIN_MENU":
        actions = set(_state_action_names(state))
        if "open_character_select" in actions:
            break
        if replace_existing_run and not replaced_run and "abandon_run" in actions:
            result = client.act(AgentAction("abandon_run"))
            modal_state = _wait_for_state_action(client, "confirm_modal", initial_payload=result.state)
            result = client.act(AgentAction("confirm_modal"))
            state = _wait_for_seed_screen(client, initial_payload=result.state)
            screen = _state_screen(state)
            replaced_run = True
            continue
        if "abandon_run" in actions:
            raise RuntimeError(
                "--seed found an existing run. Finish or abandon it first, or explicitly pass "
                "--replace-existing-run to discard it before the seeded run starts."
            )
        raise RuntimeError("--seed requires a new-run main menu with open_character_select available.")

    if screen == "MAIN_MENU":
        result = client.act(AgentAction("open_character_select"))
        state = _wait_for_seed_screen(client, initial_payload=result.state, require_character_select=True)
        screen = _state_screen(state)

    if screen != "CHARACTER_SELECT":
        raise RuntimeError(f"--seed requires CHARACTER_SELECT, received {screen}.")
    if "set_seed" not in _state_action_names(state):
        raise RuntimeError("set_seed is unavailable. The lobby may be ready, already started, or a multiplayer client.")

    result = client.act(AgentAction("set_seed", payload={"seed": requested_seed}))
    state = _wait_for_seed_screen(client, initial_payload=result.state, require_character_select=True)
    actual_seed = ((state.get("character_select") or {}).get("seed"))
    if actual_seed != requested_seed:
        raise RuntimeError(f"set_seed did not echo the requested seed (expected {requested_seed!r}, got {actual_seed!r}).")
    return state


def _state_screen(state: dict) -> str:
    agent_view = state.get("agent_view")
    if isinstance(agent_view, dict) and agent_view.get("screen"):
        return str(agent_view["screen"])
    return str(state.get("screen") or "UNKNOWN")


def _state_action_names(state: dict) -> list[str]:
    agent_view = state.get("agent_view")
    if isinstance(agent_view, dict) and (agent_view.get("available_actions") or agent_view.get("actions")):
        return action_names(agent_view)
    return action_names(state)


def _wait_for_seed_screen(
    client: HttpGameClient,
    *,
    timeout_seconds: float = 30.0,
    initial_payload: dict | None = None,
    require_character_select: bool = False,
) -> dict:
    """Health means the Mod server is alive; wait until the relevant menu screen is actionable."""
    deadline = time.monotonic() + timeout_seconds
    payload = initial_payload
    last_state: dict = {}
    while time.monotonic() < deadline:
        if payload is None:
            payload = client.get_state()
        state = unwrap_data(payload)
        screen = _state_screen(state)
        if screen == "CHARACTER_SELECT":
            return state
        if not require_character_select and screen == "MAIN_MENU":
            actions = set(_state_action_names(state))
            if "open_character_select" in actions or "abandon_run" in actions:
                return state
        last_state = state
        payload = None
        time.sleep(0.25)
    expected = "CHARACTER_SELECT" if require_character_select else "an actionable MAIN_MENU or CHARACTER_SELECT"
    raise RuntimeError(f"Timed out waiting for {expected} before setting seed; last screen was {_state_screen(last_state)}.")


def _wait_for_state_action(
    client: HttpGameClient,
    action_name: str,
    *,
    timeout_seconds: float = 15.0,
    initial_payload: dict | None = None,
) -> dict:
    """Wait for a specific transitional action, such as the abandon confirmation modal."""
    deadline = time.monotonic() + timeout_seconds
    payload = initial_payload
    last_state: dict = {}
    while time.monotonic() < deadline:
        if payload is None:
            payload = client.get_state()
        state = unwrap_data(payload)
        if action_name in _state_action_names(state):
            return state
        last_state = state
        payload = None
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {action_name}; last screen was {_state_screen(last_state)}.")


def enable_instant_mode(client: HttpGameClient, command: str = "instant") -> ActionResult:
    try:
        return client.run_console_command(command)
    except GameClientError as exc:
        if exc.code == "invalid_action" and "STS2_ENABLE_DEBUG_ACTIONS" in str(exc):
            raise RuntimeError(
                "--enable-instant requires debug actions. Start with --launch-debug-session "
                "or launch STS2 with STS2_ENABLE_DEBUG_ACTIONS=1."
            ) from exc
        raise


def _load_env_files() -> None:
    roots = [
        Path.cwd(),
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[3],
    ]
    seen: set[Path] = set()
    for root in roots:
        path = (root / ".env").resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        _load_env_file(path)


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def abandon_current_run(client: HttpGameClient) -> None:
    """Best-effort cleanup for smoke tests.

    This intentionally uses live available actions instead of assuming a screen.
    """
    with suppress(Exception):
        state = client.get_state()["data"]
        actions = set(state.get("available_actions") or [])
        if "save_and_quit" in actions:
            client.act(AgentAction("save_and_quit"))
            state = client.wait_until_actionable(20)["data"]
            actions = set(state.get("available_actions") or [])
        if "abandon_run" in actions:
            client.act(AgentAction("abandon_run"))
            state = client.wait_until_actionable(20)["data"]
            actions = set(state.get("available_actions") or [])
        if "confirm_modal" in actions:
            client.act(AgentAction("confirm_modal"))


def shutdown_game_processes() -> None:
    patterns = ("Slay the Spire 2", "SlayTheSpire2")
    pids: set[int] = set()
    for pattern in patterns:
        result = subprocess.run(["pgrep", "-f", pattern], check=False, capture_output=True, text=True)
        for line in result.stdout.splitlines():
            with suppress(ValueError):
                pids.add(int(line.strip()))

    for pid in sorted(pids):
        subprocess.run(["kill", str(pid)], check=False)
    deadline = time.monotonic() + 5
    while pids and time.monotonic() < deadline:
        remaining: set[int] = set()
        for pid in pids:
            if subprocess.run(["kill", "-0", str(pid)], check=False).returncode == 0:
                remaining.add(pid)
        pids = remaining
        if pids:
            time.sleep(0.5)

    for pid in sorted(pids):
        subprocess.run(["kill", "-9", str(pid)], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
