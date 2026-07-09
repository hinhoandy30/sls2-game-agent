from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError, model_validator

from .contracts import AgentAction, GameStateSnapshot

IndexParam = Literal["card_index", "target_index", "option_index", "potion_index"]


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action: str
    required: tuple[IndexParam, ...] = ()
    optional: tuple[IndexParam, ...] = ()

    @property
    def allowed(self) -> set[IndexParam]:
        return {*self.required, *self.optional}


ACTION_SPECS: dict[str, ActionSpec] = {
    "play_card": ActionSpec("play_card", required=("card_index",), optional=("target_index",)),
    "end_turn": ActionSpec("end_turn"),
    "choose_map_node": ActionSpec("choose_map_node", required=("option_index",)),
    "resolve_rewards": ActionSpec("resolve_rewards", optional=("option_index",)),
    "collect_rewards_and_proceed": ActionSpec("collect_rewards_and_proceed"),
    "claim_reward": ActionSpec("claim_reward", required=("option_index",)),
    "choose_reward_card": ActionSpec("choose_reward_card", required=("option_index",)),
    "skip_reward_cards": ActionSpec("skip_reward_cards"),
    "select_deck_card": ActionSpec("select_deck_card", required=("option_index",)),
    "confirm_selection": ActionSpec("confirm_selection"),
    "open_chest": ActionSpec("open_chest"),
    "choose_treasure_relic": ActionSpec("choose_treasure_relic", required=("option_index",)),
    "choose_event_option": ActionSpec("choose_event_option", required=("option_index",)),
    "choose_capstone_option": ActionSpec("choose_capstone_option", required=("option_index",)),
    "choose_bundle": ActionSpec("choose_bundle", required=("option_index",)),
    "confirm_bundle": ActionSpec("confirm_bundle"),
    "choose_rest_option": ActionSpec("choose_rest_option", required=("option_index",), optional=("target_index",)),
    "open_shop_inventory": ActionSpec("open_shop_inventory"),
    "close_shop_inventory": ActionSpec("close_shop_inventory"),
    "buy_card": ActionSpec("buy_card", required=("option_index",)),
    "buy_relic": ActionSpec("buy_relic", required=("option_index",)),
    "buy_potion": ActionSpec("buy_potion", required=("option_index",)),
    "remove_card_at_shop": ActionSpec("remove_card_at_shop"),
    "continue_run": ActionSpec("continue_run"),
    "abandon_run": ActionSpec("abandon_run"),
    "save_and_quit": ActionSpec("save_and_quit"),
    "open_character_select": ActionSpec("open_character_select"),
    "open_timeline": ActionSpec("open_timeline"),
    "close_main_menu_submenu": ActionSpec("close_main_menu_submenu"),
    "choose_timeline_epoch": ActionSpec("choose_timeline_epoch", required=("option_index",)),
    "confirm_timeline_overlay": ActionSpec("confirm_timeline_overlay"),
    "select_character": ActionSpec("select_character", required=("option_index",)),
    "embark": ActionSpec("embark"),
    "unready": ActionSpec("unready"),
    "increase_ascension": ActionSpec("increase_ascension"),
    "decrease_ascension": ActionSpec("decrease_ascension"),
    "use_potion": ActionSpec("use_potion", required=("potion_index",), optional=("target_index",)),
    "discard_potion": ActionSpec("discard_potion", required=("potion_index",)),
    "confirm_modal": ActionSpec("confirm_modal"),
    "dismiss_modal": ActionSpec("dismiss_modal"),
    "return_to_main_menu": ActionSpec("return_to_main_menu"),
    "proceed": ActionSpec("proceed"),
}

OPTION_INDEX_ACTIONS = {
    name
    for name, spec in ACTION_SPECS.items()
    if "option_index" in spec.allowed and "card_index" not in spec.allowed
}


class ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    card_index: int | None = Field(default=None)
    target_index: int | None = Field(default=None)
    option_index: int | None = Field(default=None)
    potion_index: int | None = Field(default=None)

    @model_validator(mode="after")
    def validate_against_action_spec(self) -> "ActionModel":
        spec = ACTION_SPECS.get(self.action)
        if spec is None:
            raise ValueError(f"Unsupported action: {self.action}")

        values = {
            "card_index": self.card_index,
            "target_index": self.target_index,
            "option_index": self.option_index,
            "potion_index": self.potion_index,
        }
        for param in spec.required:
            if values[param] is None:
                raise ValueError(f"{self.action} requires {param}")
        for param, value in values.items():
            if value is not None and param not in spec.allowed:
                raise ValueError(f"{self.action} does not allow {param}")
        return self

    def to_agent_action(self) -> AgentAction:
        return AgentAction(
            action=self.action,
            card_index=self.card_index,
            target_index=self.target_index,
            option_index=self.option_index,
            potion_index=self.potion_index,
        )


def action_spec_prompt_options(state: GameStateSnapshot) -> list[dict[str, Any]]:
    return [
        {
            "action": action,
            "required_params": list((ACTION_SPECS.get(action) or ActionSpec(action)).required),
            "optional_params": list((ACTION_SPECS.get(action) or ActionSpec(action)).optional),
            "options": _options_for_action(action, state.state),
        }
        for action in state.available_actions
        if action in ACTION_SPECS
    ]


def parse_llm_action_payload(action_payload: dict[str, Any], state: GameStateSnapshot) -> AgentAction:
    normalized = _normalize_payload(dict(action_payload), state)
    try:
        return ActionModel.model_validate(normalized).to_agent_action()
    except PydanticValidationError as exc:
        raise ValueError(f"Invalid action payload for ActionSpec: {exc}") from exc


def _normalize_payload(payload: dict[str, Any], state: GameStateSnapshot) -> dict[str, Any]:
    action = str(payload.get("action") or "")
    if action in OPTION_INDEX_ACTIONS and payload.get("option_index") is None:
        if payload.get("card_index") is not None:
            payload["option_index"] = payload.pop("card_index")
        elif payload.get("target_index") is not None:
            payload["option_index"] = payload.pop("target_index")
        else:
            inferred = _infer_option_index(action, state.state)
            if inferred is not None:
                payload["option_index"] = inferred

    if action in {"use_potion", "discard_potion"} and payload.get("potion_index") is None and payload.get("option_index") is not None:
        payload["potion_index"] = payload.pop("option_index")

    return payload


def _infer_option_index(action_name: str, raw: dict[str, Any]) -> int | None:
    for candidate in _options_for_action(action_name, raw):
        index = candidate.get("option_index")
        if isinstance(index, int):
            return index
    return None


def _options_for_action(action_name: str, raw: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if action_name == "choose_map_node":
        candidates = (raw.get("map") or {}).get("available_nodes") or []
    elif action_name == "choose_event_option":
        candidates = (raw.get("event") or {}).get("options") or []
    elif action_name == "select_deck_card":
        candidates = (raw.get("selection") or {}).get("cards") or (raw.get("selection") or {}).get("options") or []
    elif action_name in {"claim_reward", "choose_reward_card", "choose_treasure_relic"}:
        candidates = (raw.get("reward") or {}).get("rewards") or (raw.get("reward") or {}).get("cards") or []
    elif action_name in {"buy_card", "buy_relic", "buy_potion"}:
        candidates = (raw.get("shop") or {}).get("items") or []
    elif action_name in {"choose_rest_option", "choose_bundle", "choose_capstone_option"}:
        candidates = (raw.get("selection") or {}).get("options") or (raw.get("event") or {}).get("options") or []

    options: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("is_locked", False):
            continue
        index = candidate.get("index")
        if isinstance(index, int):
            compact = {"option_index": index}
            for key in ("node_type", "row", "col", "event_id", "label", "name", "card_id", "relic_id", "potion_id", "price"):
                if key in candidate:
                    compact[key] = candidate[key]
            options.append(compact)
    return options
