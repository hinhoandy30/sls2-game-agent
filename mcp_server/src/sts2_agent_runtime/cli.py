from __future__ import annotations

import argparse
import os
import subprocess
import time
from contextlib import suppress
from pathlib import Path

from .contracts import AgentAction
from .client import HttpGameClient
from .llm import GAMEPLAY_LLM_SCREENS, LLMScreenRouter, OpenAICompatiblePolicy
from .runtime import AgentRuntime, RuntimeConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MVP0 STS2 agent runtime.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output-dir", default="runs/agent-runtime")
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--wait-timeout", type=float, default=20.0)
    parser.add_argument("--launch-steam", action="store_true")
    parser.add_argument("--steam-url", default="steam://run/2868840")
    parser.add_argument("--resume", action="store_true", help="Connect to the current game state and continue from there.")
    parser.add_argument("--stop-after-first-combat", action="store_true")
    parser.add_argument("--stop-on-reward-after-combat", action="store_true")
    parser.add_argument("--policy", choices=["heuristic", "llm"], default="heuristic")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-screens", choices=["gameplay", "all"], default="gameplay")
    parser.add_argument("--cleanup-only", action="store_true")
    parser.add_argument("--abandon-run", action="store_true")
    parser.add_argument("--shutdown-game", action="store_true")
    args = parser.parse_args(argv)
    _load_env_files()

    if args.launch_steam:
        subprocess.run(["open", args.steam_url], check=False)

    client = HttpGameClient(base_url=args.base_url)
    if args.launch_steam:
        _wait_for_health(client, timeout_seconds=120)

    if args.cleanup_only:
        if args.abandon_run:
            abandon_current_run(client)
        if args.shutdown_game:
            shutdown_game_processes()
        return 0

    router = None
    if args.policy == "llm":
        screens = None if args.llm_screens == "gameplay" else {
            "MAIN_MENU",
            "CHARACTER_SELECT",
            *GAMEPLAY_LLM_SCREENS,
            "GAME_OVER",
        }
        router = LLMScreenRouter(
            llm_policy=OpenAICompatiblePolicy(model=args.llm_model),
            llm_screens=screens,
        )

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
    )
    summary = runtime.run()
    print(summary.to_dict())
    if args.abandon_run:
        abandon_current_run(client)
    if args.shutdown_game:
        shutdown_game_processes()
    return 0


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
