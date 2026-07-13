# Delta for Stable Combat Planning

## ADDED Requirements

### Requirement: LLM Combat Policy Plans With Stable Legal Actions

When the current combat state exposes stable card and enemy identities, the LLM
combat Policy SHALL return a bounded action plan made only of current
`legal_action_id` values.

#### Scenario: Planning a normal combat turn

- **GIVEN** the combat state provides stable identities for all playable combat
  actions
- **WHEN** the LLM Policy decides
- **THEN** it returns one bounded ordered action plan
- **AND** every plan item has exactly one `legal_action_id`
- **AND** no plan item contains `card_index` or `target_index`

#### Scenario: Bridge lacks stable identity

- **GIVEN** a playable combat action lacks the stable ID required to resolve it
- **WHEN** the LLM Policy decides
- **THEN** it uses the existing single-action contract
- **AND** it records the fallback reason in decision metadata

### Requirement: Runtime Executes A Stable Plan Without Recalling The LLM

Runtime SHALL execute one stable action plan sequentially with a fresh state
between actions, and SHALL not call the LLM again until that plan completes or
stops.

#### Scenario: A card moves after an earlier action

- **GIVEN** a later plan item references a current card instance
- **WHEN** an earlier action changes the hand order
- **THEN** Runtime resolves the later card by instance ID in fresh state
- **AND** it executes the intended current card or safely stops the plan

