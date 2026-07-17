# Design: Card Priority Knowledge Sample

## Scope

This change implements one complete, reviewable slice of card strategy
knowledge. It covers five Ironclad cards selected for materially different
deck-development decisions: combat deck growth, exhaust and draw, draw
lockout, health-for-energy conversion, and skill-exhaust engines.

## Data Contract

The existing `sts2-card-priority-strategy.v1` schema remains the source of
truth. Files live under:

```text
mcp_server/data/knowledge/v1/strategy/card_priorities/<CARD_ID>.json
```

Each entry keeps conditional strategy separate from the corresponding
`cards/<CARD_ID>.json` fact file. The entry records baseline priority,
role tags, favorable and unfavorable conditions, pick-versus-skip comparisons,
upgrade priority, notes, and source references.

Strategy claims must name their conditions. A file may describe a card as
strong when a deck has a specific need, but it must not claim the card is
universally correct. Exact card text, current cost, and legality continue to
come from live state and the card fact entry.

## Retrieval

`KnowledgeProvider.for_state` collects candidate IDs from:

- `reward.cards[]` while reward-card choices are visible;
- `shop.cards[]` while shop-card choices are visible.

For each candidate ID, the provider loads both the existing card fact and the
optional card-priority entry. Priority entries are returned in a new
`KnowledgeContext.card_priorities` list and use `card_priority:<CARD_ID>` refs.
Fact sources and strategy sources remain separately traceable.

The provider does not inject card-priority entries for cards that only appear
in the combat hand. Combat policy continues to receive card facts without
reward-selection advice.

## Prompt Contract

`PromptBuilder` includes `card_priorities` as a separately sorted field in the
canonical knowledge packet. Entries sort by `card_id`, and duplicate candidate
IDs collapse to one entry. Equivalent candidate sets therefore produce stable
knowledge packet hashes regardless of source-list order.

## Missing And Invalid Data

A missing priority file is an expected partial-coverage condition: the card
fact remains available and decision-making continues without a strategy entry.
Malformed priority files fail Pydantic validation with their file path; they do
not silently degrade to an unvalidated dictionary.

## Initial Entries

- `ANGER`: copying pressure, deck growth, and zero-cost damage conditions.
- `BURNING_PACT`: exhaust target quality, draw need, and upgrade value.
- `BATTLE_TRANCE`: zero-cost draw, draw lockout, and sequencing conditions.
- `OFFERING`: health cost, energy conversion, draw volume, and survival margin.
- `CORRUPTION`: skill density, exhaust payoffs, fight duration, and setup cost.

Each entry must cite version-relevant fact and strategy sources retrieved during
implementation. Unsupported numerical claims are excluded.

## Verification

- Validate all five JSON files with `sts2-validate-knowledge`.
- Test reward and shop candidate lookup, missing-entry fallback, deduplication,
  and stable ordering.
- Test that combat-hand-only states do not receive card-priority entries.
- Test that prompt canonicalization and knowledge hashes include the separate
  strategy field deterministically.
- Run the focused Runtime unit tests and full OpenSpec validation.

## Delivery

Submit the OpenSpec artifacts, Runtime integration, tests, and initial entries
from a feature branch into `dev`. The pull request must include verification
evidence and exclude machine-specific files. Archive the change only after the
implementation is merged and verified.
