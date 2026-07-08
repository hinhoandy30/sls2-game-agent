from __future__ import annotations

from .contracts import GameStateSnapshot, KnowledgeContext


class KnowledgeProvider:
    def for_state(self, state: GameStateSnapshot) -> KnowledgeContext:
        raw = state.state
        refs: list[str] = []

        combat = raw.get("combat") if isinstance(raw.get("combat"), dict) else {}
        for enemy in combat.get("enemies") or []:
            enemy_id = enemy.get("enemy_id") or enemy.get("id")
            if enemy_id:
                refs.append(f"monster:{enemy_id}")
        for card in combat.get("hand") or []:
            card_id = card.get("card_id") or card.get("id")
            if card_id:
                refs.append(f"card:{card_id}")

        run = raw.get("run") if isinstance(raw.get("run"), dict) else {}
        for potion in run.get("potions") or []:
            potion_id = potion.get("potion_id")
            if potion_id:
                refs.append(f"potion:{potion_id}")

        return KnowledgeContext(run_id=state.run_id, refs=sorted(set(refs)))
