from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol
from urllib import error, request

from .contracts import ActionResult, AgentAction


class GameClient(Protocol):
    def health(self) -> dict[str, Any]: ...
    def get_state(self) -> dict[str, Any]: ...
    def get_available_actions(self) -> list[dict[str, Any]]: ...
    def act(self, action: AgentAction) -> ActionResult: ...
    def run_console_command(self, command: str) -> ActionResult: ...
    def wait_until_actionable(self, timeout_seconds: float) -> dict[str, Any]: ...


class GameClientError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details

    def to_error(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
            "details": self.details,
        }


PASSIVE_ACTIONS = {"save_and_quit", "discard_potion"}
COMBAT_DECISION_ACTIONS = {"play_card", "end_turn"}
SCREEN_DECISION_ACTIONS: dict[str, set[str]] = {
    "MAIN_MENU": {"continue_run", "open_character_select", "open_timeline", "abandon_run"},
    "CHARACTER_SELECT": {"select_character", "set_seed", "embark", "increase_ascension", "decrease_ascension", "unready"},
    "MAP": {"choose_map_node", "use_potion", "discard_potion"},
    "COMBAT": {"play_card", "end_turn", "use_potion", "discard_potion"},
    "REWARD": {"claim_reward", "choose_reward_card", "skip_reward_cards", "collect_rewards_and_proceed", "resolve_rewards"},
    "CARD_SELECTION": {"select_deck_card", "confirm_selection"},
    "BUNDLE_SELECTION": {"choose_bundle", "confirm_bundle"},
    "EVENT": {"choose_event_option", "proceed"},
    "SHOP": {"open_shop_inventory", "close_shop_inventory", "buy_card", "buy_relic", "buy_potion", "remove_card_at_shop", "proceed"},
    "REST": {"choose_rest_option", "select_deck_card", "confirm_selection", "proceed"},
    "CHEST": {"open_chest", "choose_treasure_relic", "proceed"},
    "MODAL": {"confirm_modal", "dismiss_modal"},
    "GAME_OVER": {"return_to_main_menu"},
}


def unwrap_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def action_names(state: dict[str, Any]) -> list[str]:
    raw_actions = state.get("available_actions") or state.get("actions") or []
    names: list[str] = []
    for action in raw_actions:
        if isinstance(action, str):
            names.append(action)
        elif isinstance(action, dict) and isinstance(action.get("name"), str):
            names.append(action["name"])
    return names


def is_actionable_state(state_payload: dict[str, Any]) -> bool:
    state = unwrap_data(state_payload)
    screen = str(state.get("screen") or "")
    names = set(action_names(state))
    if not screen or screen == "UNKNOWN" or not names:
        return False
    if screen == "COMBAT":
        return bool(names & COMBAT_DECISION_ACTIONS)
    expected = SCREEN_DECISION_ACTIONS.get(screen)
    if expected is None:
        return bool(names - PASSIVE_ACTIONS)
    return bool(names & expected)


class HttpGameClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        read_timeout: float = 10.0,
        action_timeout: float = 30.0,
        poll_interval: float = 0.25,
    ) -> None:
        self.base_url = (base_url or os.getenv("STS2_API_BASE_URL") or "http://127.0.0.1:8080").rstrip("/")
        self.read_timeout = read_timeout
        self.action_timeout = action_timeout
        self.poll_interval = poll_interval

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", timeout=self.read_timeout)

    def get_state(self) -> dict[str, Any]:
        return self._request("GET", "/state", timeout=self.read_timeout)

    def get_available_actions(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/actions/available", timeout=self.read_timeout)
        actions = unwrap_data(payload).get("actions")
        return list(actions) if isinstance(actions, list) else []

    def act(self, action: AgentAction) -> ActionResult:
        payload = self._request(
            "POST",
            "/action",
            payload=action.to_request(),
            timeout=self.action_timeout,
        )
        return ActionResult.from_payload(payload, action=action.action)

    def run_console_command(self, command: str) -> ActionResult:
        payload = self._request(
            "POST",
            "/action",
            payload={
                "action": "run_console_command",
                "command": command,
                "client_context": {"source": "agent-runtime", "tool_name": "run_console_command"},
            },
            timeout=self.action_timeout,
        )
        return ActionResult.from_payload(payload, action="run_console_command")

    def wait_until_actionable(self, timeout_seconds: float) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.1, timeout_seconds)
        last_state: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last_state = self.get_state()
            if is_actionable_state(last_state):
                return last_state
            time.sleep(self.poll_interval)

        raise GameClientError(
            "wait_until_actionable_timeout",
            "Timed out waiting for a fresh actionable STS2 state.",
            retryable=True,
            details={"last_state": unwrap_data(last_state or {})},
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float,
    ) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        http_request = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=timeout) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            try:
                decoded = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise GameClientError(
                    "http_error",
                    f"STS2 mod API returned HTTP {exc.code} for {path}.",
                    retryable=500 <= exc.code < 600,
                    details={"path": path, "http_status": exc.code},
                ) from exc
        except error.URLError as exc:
            raise GameClientError(
                "connection_error",
                f"Cannot reach STS2 mod API at {self.base_url}.",
                retryable=True,
                details={"path": path, "reason": str(getattr(exc, "reason", exc))},
            ) from exc

        if not decoded.get("ok", False):
            err = decoded.get("error") if isinstance(decoded.get("error"), dict) else {}
            raise GameClientError(
                str(err.get("code") or "api_error"),
                str(err.get("message") or "STS2 API request failed."),
                retryable=bool(err.get("retryable", False)),
                details=err.get("details"),
            )
        return decoded
