from __future__ import annotations

from typing import Any

from .contracts import AgentAction, GameStateSnapshot


def build_legal_actions(state: GameStateSnapshot) -> list[dict[str, Any]]:
    raw = state.state
    available = set(state.available_actions)
    legal: list[dict[str, Any]] = []

    if "play_card" in available:
        for card in ((raw.get("combat") or {}).get("hand") or []):
            if not isinstance(card, dict) or not card.get("playable", False):
                continue
            card_index = card.get("index")
            if not isinstance(card_index, int):
                continue
            base = {
                "action": "play_card",
                "card_index": card_index,
                "card_id": card.get("card_id"),
                "name": card.get("name"),
                "energy_cost": card.get("energy_cost"),
            }
            if card.get("requires_target"):
                for target_index in card.get("valid_target_indices") or []:
                    if isinstance(target_index, int):
                        legal.append(_with_id({**base, "target_index": target_index}))
            else:
                legal.append(_with_id(base))

    if "use_potion" in available or "discard_potion" in available:
        for potion in ((raw.get("run") or {}).get("potions") or []):
            if not isinstance(potion, dict) or not potion.get("occupied", False):
                continue
            potion_index = potion.get("index")
            if not isinstance(potion_index, int):
                continue
            if "use_potion" in available and potion.get("can_use", False):
                base = {
                    "action": "use_potion",
                    "potion_index": potion_index,
                    "potion_id": potion.get("potion_id"),
                    "name": potion.get("name"),
                }
                if potion.get("requires_target"):
                    for target_index in potion.get("valid_target_indices") or []:
                        if isinstance(target_index, int):
                            legal.append(_with_id({**base, "target_index": target_index}))
                else:
                    legal.append(_with_id(base))
            if "discard_potion" in available and potion.get("can_discard", False):
                legal.append(
                    _with_id(
                        {
                            "action": "discard_potion",
                            "potion_index": potion_index,
                            "potion_id": potion.get("potion_id"),
                            "name": potion.get("name"),
                        }
                    )
                )

    _add_option_actions(legal, available, "choose_map_node", (raw.get("map") or {}).get("available_nodes") or [], "map")
    _add_option_actions(legal, available, "choose_event_option", (raw.get("event") or {}).get("options") or [], "event")
    _add_option_actions(legal, available, "select_deck_card", (raw.get("selection") or {}).get("cards") or (raw.get("selection") or {}).get("options") or [], "selection")
    _add_option_actions(legal, available, "claim_reward", (raw.get("reward") or {}).get("rewards") or [], "reward")
    _add_option_actions(legal, available, "choose_reward_card", (raw.get("reward") or {}).get("cards") or [], "reward_card")
    _add_option_actions(legal, available, "choose_treasure_relic", (raw.get("reward") or {}).get("rewards") or [], "treasure")
    _add_option_actions(legal, available, "choose_rest_option", (raw.get("rest") or {}).get("options") or (raw.get("selection") or {}).get("options") or [], "rest")
    _add_option_actions(legal, available, "buy_card", (raw.get("shop") or {}).get("cards") or (raw.get("shop") or {}).get("items") or [], "shop_card")
    _add_option_actions(legal, available, "buy_relic", (raw.get("shop") or {}).get("relics") or (raw.get("shop") or {}).get("items") or [], "shop_relic")
    _add_option_actions(legal, available, "buy_potion", (raw.get("shop") or {}).get("potions") or (raw.get("shop") or {}).get("items") or [], "shop_potion")

    for action in sorted(available & _SIMPLE_ACTIONS):
        legal.append(_with_id({"action": action}))

    return legal


def action_from_legal_action_id(legal_action_id: str, state: GameStateSnapshot) -> AgentAction:
    for legal in build_legal_actions(state):
        if legal.get("id") == legal_action_id:
            return AgentAction(
                action=str(legal["action"]),
                card_index=legal.get("card_index") if isinstance(legal.get("card_index"), int) else None,
                target_index=legal.get("target_index") if isinstance(legal.get("target_index"), int) else None,
                option_index=legal.get("option_index") if isinstance(legal.get("option_index"), int) else None,
                potion_index=legal.get("potion_index") if isinstance(legal.get("potion_index"), int) else None,
                legal_action_id=legal_action_id,
            )
    raise ValueError(f"legal_action_id is not available in the latest state: {legal_action_id}")


def _add_option_actions(legal: list[dict[str, Any]], available: set[str], action: str, options: list[Any], namespace: str) -> None:
    if action not in available:
        return
    for option in options:
        if not isinstance(option, dict) or option.get("is_locked", False):
            continue
        index = option.get("index")
        if not isinstance(index, int):
            continue
        item: dict[str, Any] = {
            "action": action,
            "option_index": index,
            "namespace": namespace,
        }
        for key in ("node_type", "row", "col", "event_id", "label", "name", "card_id", "relic_id", "potion_id", "price"):
            if key in option:
                item[key] = option[key]
        legal.append(_with_id(item))


def _with_id(action: dict[str, Any]) -> dict[str, Any]:
    parts = [str(action["action"])]
    for key in ("card_index", "potion_index", "option_index", "target_index"):
        value = action.get(key)
        if value is not None:
            parts.append(f"{key.removesuffix('_index')}_{value}")
    for key in ("card_id", "potion_id", "node_type", "event_id", "name"):
        value = action.get(key)
        if value:
            parts.append(_safe_id(str(value)))
            break
    return {"id": "_".join(parts), **action}


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value).strip("-")[:48]


_SIMPLE_ACTIONS = {
    "end_turn",
    "collect_rewards_and_proceed",
    "skip_reward_cards",
    "confirm_selection",
    "open_chest",
    "confirm_bundle",
    "open_shop_inventory",
    "close_shop_inventory",
    "remove_card_at_shop",
    "continue_run",
    "abandon_run",
    "save_and_quit",
    "open_character_select",
    "open_timeline",
    "close_main_menu_submenu",
    "confirm_timeline_overlay",
    "embark",
    "unready",
    "increase_ascension",
    "decrease_ascension",
    "confirm_modal",
    "dismiss_modal",
    "return_to_main_menu",
    "proceed",
}
