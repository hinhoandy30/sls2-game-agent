# Design: 战斗检查协议与固定种子开局

## Combat policy

CombatAgent 保持为唯一的战斗策略决策者。它接收 live state、怪物知识、牌组上下文和一份
固定的检查协议，输出 stable `legal_action_id` action plan 以及简短 `combat_audit`。

`combat_audit` 是可观察结论，不要求或存储模型的长推理链：

```json
{
  "primary_target_id": "enemy_1|null",
  "lethal_this_turn": "yes|no|unknown",
  "defense_posture": "lethal|full_block|accept_damage_for_tempo|unavoidable_damage|unknown",
  "risk_summary_zh": "short factual summary",
  "replan_after": [
    {
      "legal_action_id": "play_card_card-123",
      "reason": "draw_cards|random_effect|card_generation|discard_or_exhaust|entity_missing|unknown_complex_effect"
    }
  ]
}
```

The model must only claim a kill or damage estimate when supported by the current state and selected actions.
If draw/discard/exhaust pile contents are not exposed by the Mod, it must not claim that a specific card will be
drawn next turn; whole-deck composition is only probabilistic context.

## Replanning boundary

The policy declares the earliest relevant boundary in `combat_audit.replan_after`, including the stable action ID
that creates it. Runtime validates the allowlisted reason and requires that action to be the final item in the plan,
records the audit, and stops after executing it. Runtime already re-reads state after each action and continues to
stop on screen changes or stale stable IDs.

V1 does not infer card effects from localized rules text. It applies declared boundaries conservatively: a plan may
include a boundary action, but actions after it are not executed. Unknown or undeclared complex effects retain the
existing fresh-state and stable-ID validation behavior.

## Seeded runs

`StartRunLobby.SetSeed(string)` cannot be called from v0.107.1's standard singleplayer UI: it notifies
`NCharacterSelectScreen.SeedChanged()`, which deliberately throws in standard mode. The Mod instead invokes
the non-public setter of `StartRunLobby.Seed`, which is the state consumed by the normal embark path, without
broadcasting to peers or invoking that unsupported UI callback. The Mod exposes this as `set_seed` only when:

- the active screen is `CHARACTER_SELECT`;
- the lobby is singleplayer or host, not a multiplayer client;
- the local player has not readied/embarked; and
- the request contains a non-empty bounded seed string.

The C# action returns a fresh state. It verifies the lobby seed matches the requested value before reporting
`completed`; otherwise it reports a pending transition or an API error. Python's CLI bootstrap may navigate from
the main menu to character selection, set the seed, then let the normal deterministic character-select flow embark.

## Alternatives rejected

- Full tactical solver: cannot safely model hidden draw order, random effects and all card mechanics yet.
- Prompt-only handling of plan boundaries: it cannot guarantee that a model-generated action after a draw is not
  executed; Runtime must enforce the declared boundary.
- Debug-console seed commands: they would require debug mode and are unsuitable for normal reproducible evaluation.
