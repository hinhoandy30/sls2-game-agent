from __future__ import annotations

from typing import Protocol

from .contracts import AgentAction, GameStateSnapshot, KnowledgeContext, PolicyDecision


class Policy(Protocol):
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision: ...


def _raw(snapshot: GameStateSnapshot) -> dict:
    return snapshot.state


class MenuPolicy:
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        actions = set(state.available_actions)
        if "continue_run" in actions:
            return PolicyDecision.action_decision(AgentAction("continue_run"), reason="继续当前 run。")
        if "open_character_select" in actions:
            return PolicyDecision.action_decision(AgentAction("open_character_select"), reason="开始新 run，打开角色选择。")
        return PolicyDecision.needs_human("主菜单没有 continue_run 或 open_character_select。")


class CharacterSelectPolicy:
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        actions = set(state.available_actions)
        character_select = _raw(state).get("character_select") or {}
        if "embark" in actions and character_select.get("can_embark", True):
            return PolicyDecision.action_decision(AgentAction("embark"), reason="角色已选择，可以出发。")

        characters = character_select.get("characters") or character_select.get("options") or []
        for character in characters:
            cid = str(character.get("character_id") or character.get("id") or "").upper()
            if "IRONCLAD" in cid and character.get("unlocked", True):
                index = character.get("index")
                if isinstance(index, int):
                    return PolicyDecision.action_decision(
                        AgentAction("select_character", option_index=index),
                        reason="MVP0 默认选择 Ironclad。",
                    )

        if "select_character" in actions and characters:
            index = characters[0].get("index", 0)
            return PolicyDecision.action_decision(AgentAction("select_character", option_index=int(index)), reason="选择第一个可用角色。")
        return PolicyDecision.needs_human("无法在角色选择界面找到可选角色。")


class MapPolicy:
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        map_payload = _raw(state).get("map") or {}
        nodes = map_payload.get("available_nodes") or []
        if "choose_map_node" in state.available_actions and nodes:
            preferred = next((node for node in nodes if node.get("node_type") == "Monster"), None)
            selected = preferred or nodes[0]
            return PolicyDecision.action_decision(
                AgentAction("choose_map_node", option_index=int(selected.get("index", 0))),
                reason="MVP0 优先选择普通怪节点，否则选择第一个可走地图节点。",
            )
        return PolicyDecision.needs_human("地图没有可选择节点。")


class RewardPolicy:
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        actions = set(state.available_actions)
        if "collect_rewards_and_proceed" in actions:
            return PolicyDecision.action_decision(AgentAction("collect_rewards_and_proceed"), reason="MVP0 使用高层奖励推进动作。")
        if "skip_reward_cards" in actions:
            return PolicyDecision.action_decision(AgentAction("skip_reward_cards"), reason="MVP0 默认跳过选牌。")
        reward = _raw(state).get("reward") or {}
        rewards = reward.get("rewards") or []
        if "claim_reward" in actions and rewards:
            return PolicyDecision.action_decision(AgentAction("claim_reward", option_index=int(rewards[0].get("index", 0))), reason="领取第一个可领取奖励。")
        if "proceed" in actions:
            return PolicyDecision.action_decision(AgentAction("proceed"), reason="奖励已处理，继续。")
        return PolicyDecision.needs_human("奖励界面没有 MVP0 可处理动作。")


class CombatPolicyV0:
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        raw = _raw(state)
        combat = raw.get("combat") or {}
        hand = combat.get("hand") or []
        enemies = [enemy for enemy in (combat.get("enemies") or []) if enemy.get("is_alive", True) and enemy.get("is_hittable", True)]

        if "play_card" in state.available_actions:
            attacks = [card for card in hand if card.get("playable") and card.get("card_type") == "Attack"]
            playable = attacks or [card for card in hand if card.get("playable")]
            for card in playable:
                index = card.get("index")
                if not isinstance(index, int):
                    continue
                if card.get("requires_target"):
                    targets = card.get("valid_target_indices") or []
                    if not targets and enemies:
                        targets = [enemies[0].get("index", 0)]
                    if targets:
                        return PolicyDecision.action_decision(
                            AgentAction("play_card", card_index=index, target_index=int(targets[0])),
                            reason=f"打出可用牌 {card.get('card_id') or card.get('name')} 并选择第一个合法目标。",
                            confidence=0.55,
                            used_knowledge=knowledge.refs,
                        )
                    continue
                return PolicyDecision.action_decision(
                    AgentAction("play_card", card_index=index),
                    reason=f"打出不需要目标的可用牌 {card.get('card_id') or card.get('name')}。",
                    confidence=0.55,
                    used_knowledge=knowledge.refs,
                )

        if "end_turn" in state.available_actions:
            return PolicyDecision.action_decision(AgentAction("end_turn"), reason="没有可用出牌，结束回合。")
        return PolicyDecision.wait("战斗界面暂时没有 play_card 或 end_turn，等待 action window。")


class ModalPolicy:
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        if "confirm_modal" in state.available_actions:
            return PolicyDecision.action_decision(AgentAction("confirm_modal"), reason="确认当前 modal。")
        if "dismiss_modal" in state.available_actions:
            return PolicyDecision.action_decision(AgentAction("dismiss_modal"), reason="关闭当前 modal。")
        return PolicyDecision.needs_human("Modal 没有可处理动作。")


class SelectionPolicy:
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        selection = _raw(state).get("selection") or {}
        options = selection.get("cards") or selection.get("options") or []
        if "select_deck_card" in state.available_actions and options:
            return PolicyDecision.action_decision(
                AgentAction("select_deck_card", option_index=int(options[0].get("index", 0))),
                reason="MVP0 选择第一个 selection option。",
            )
        if "confirm_selection" in state.available_actions:
            return PolicyDecision.action_decision(AgentAction("confirm_selection"), reason="确认 selection。")
        return PolicyDecision.needs_human("Selection 没有可处理动作。")


class EventPolicy:
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        event = _raw(state).get("event") or {}
        options = event.get("options") or []
        if "choose_event_option" not in state.available_actions:
            if "proceed" in state.available_actions:
                return PolicyDecision.action_decision(AgentAction("proceed"), reason="事件已结束，继续。")
            return PolicyDecision.needs_human("事件没有 choose_event_option 或 proceed。")

        if event.get("event_id") == "NEOW":
            for option in options:
                if option.get("index") == 1 and not option.get("is_locked", False):
                    return PolicyDecision.action_decision(
                        AgentAction("choose_event_option", option_index=1),
                        reason="Neow 事件 MVP0 选择钓鱼竿，避免复杂选牌分支。",
                    )

        for option in options:
            if not option.get("is_locked", False) and not option.get("will_kill_player", False):
                return PolicyDecision.action_decision(
                    AgentAction("choose_event_option", option_index=int(option.get("index", 0))),
                    reason="选择第一个未锁定且不会致死的事件选项。",
                )
        return PolicyDecision.needs_human("事件没有安全可选项。")


class PassthroughPolicy:
    def __init__(self, action_order: list[str]) -> None:
        self.action_order = action_order

    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision:
        for action in self.action_order:
            if action in state.available_actions:
                return PolicyDecision.action_decision(AgentAction(action), reason=f"MVP0 passthrough 执行 {action}。")
        return PolicyDecision.needs_human(f"{state.screen} 没有 MVP0 passthrough 可处理动作。")


class ScreenRouter:
    def __init__(self) -> None:
        self.policies: dict[str, Policy] = {
            "MAIN_MENU": MenuPolicy(),
            "CHARACTER_SELECT": CharacterSelectPolicy(),
            "MAP": MapPolicy(),
            "COMBAT": CombatPolicyV0(),
            "REWARD": RewardPolicy(),
            "MODAL": ModalPolicy(),
            "CARD_SELECTION": SelectionPolicy(),
            "CHEST": PassthroughPolicy(["open_chest", "choose_treasure_relic", "proceed"]),
            "EVENT": EventPolicy(),
            "SHOP": PassthroughPolicy(["open_shop_inventory", "close_shop_inventory", "proceed"]),
            "REST": PassthroughPolicy(["choose_rest_option", "proceed"]),
            "GAME_OVER": PassthroughPolicy(["return_to_main_menu"]),
        }

    def select(self, state: GameStateSnapshot) -> Policy:
        policy = self.policies.get(state.screen)
        if policy is None:
            return PassthroughPolicy([])
        return policy
