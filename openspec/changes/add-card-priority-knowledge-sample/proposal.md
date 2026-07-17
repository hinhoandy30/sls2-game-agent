# Proposal: Add Card Priority Knowledge Sample

## Why

The repository already contains structured facts for card IDs and a validated
`CardPriorityKnowledgeFile` schema, but there are no card-priority entries and
the Runtime does not retrieve that strategy layer. Reward and shop decisions
therefore receive card mechanics without conditional guidance about picking,
skipping, or upgrading a card.

## What Changes

- Add five reviewed Ironclad card-priority entries for `ANGER`,
  `BURNING_PACT`, `BATTLE_TRANCE`, `OFFERING`, and `CORRUPTION`.
- Retrieve card facts and card-priority strategy by stable `card_id` from
  reward-card and shop-card candidates.
- Keep card facts and card-priority strategy in separate prompt fields and
  source references.
- Validate and test missing-entry fallback, deduplication, deterministic
  ordering, and compact prompt injection.

## Non-goals

- Do not assign priorities to every card in this change.
- Do not add strategy entries for non-Ironclad cards.
- Do not add combat play-order tactics or alter combat action planning.
- Do not add monster, event, relic, or potion strategy files.
- Do not treat a baseline priority as an unconditional tier rating.

## Impact

RunDevelopmentAgent can use a small, auditable strategy sample when choosing
reward or shop cards. Knowledge maintainers gain a reviewed pattern that can be
extended card by card without changing the game-fact files.
