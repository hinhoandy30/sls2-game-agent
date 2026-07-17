# Delta for Card Priority Knowledge

## ADDED Requirements

### Requirement: Card Priority Knowledge Is Retrieved For Choice Candidates

The KnowledgeProvider SHALL retrieve optional card-priority strategy by stable
`card_id` for visible reward-card and shop-card candidates.

#### Scenario: Reward cards include a covered card

- **GIVEN** `reward.cards[]` contains a card with a reviewed priority file
- **WHEN** KnowledgeProvider builds context
- **THEN** it returns that card's fact entry
- **AND** it returns the strategy entry in `card_priorities`
- **AND** the context includes a `card_priority:<CARD_ID>` reference.

#### Scenario: Shop cards include duplicate IDs

- **GIVEN** `shop.cards[]` contains the same `card_id` more than once
- **WHEN** KnowledgeProvider builds context
- **THEN** it returns one priority entry for that ID.

### Requirement: Card Facts And Strategy Remain Separate

The Runtime SHALL keep verifiable card mechanics separate from conditional
pick, skip, and upgrade guidance.

#### Scenario: Prompt contains card knowledge

- **WHEN** PromptBuilder canonicalizes a KnowledgeContext with facts and
  priority strategy
- **THEN** card mechanics appear under `cards`
- **AND** conditional strategy appears under `card_priorities`
- **AND** each layer retains its own source references.

### Requirement: Partial Strategy Coverage Degrades Safely

Missing card-priority files SHALL NOT prevent reward or shop decisions.

#### Scenario: Candidate has facts but no priority entry

- **GIVEN** a candidate card has a valid card fact file
- **AND** no matching priority strategy file exists
- **WHEN** KnowledgeProvider builds context
- **THEN** it returns the card fact
- **AND** it omits a priority entry for that card
- **AND** it does not raise an error.

### Requirement: Priority Knowledge Is Choice-Scoped And Deterministic

Card-priority strategy SHALL be injected only for card-choice contexts and
shall be ordered deterministically by `card_id`.

#### Scenario: Covered card appears only in combat hand

- **GIVEN** a covered card appears in `combat.hand[]`
- **AND** it is not a reward or shop candidate
- **WHEN** KnowledgeProvider builds context
- **THEN** the card fact may be returned
- **AND** its card-priority strategy is not returned.

#### Scenario: Candidate order changes

- **GIVEN** two states contain the same covered candidate IDs in different
  source-list orders
- **WHEN** PromptBuilder canonicalizes both knowledge packets
- **THEN** the `card_priorities` order is identical
- **AND** the knowledge packet hashes are identical.

### Requirement: The Initial Sample Is Reviewed And Traceable

The first card-priority batch SHALL cover only Ironclad cards: `ANGER`,
`BURNING_PACT`, `BATTLE_TRANCE`, `OFFERING`, and `CORRUPTION`, with conditional
guidance and non-placeholder sources.

#### Scenario: Knowledge validation runs

- **GIVEN** the five initial priority files
- **WHEN** `sts2-validate-knowledge` validates the knowledge root
- **THEN** every file matches `sts2-card-priority-strategy.v1`
- **AND** every filename matches its `card_id`
- **AND** every source has a real URL and retrieval date.
