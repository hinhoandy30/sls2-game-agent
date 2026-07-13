# Delta for Stable Combat Action Identities

## ADDED Requirements

### Requirement: Combat State Exposes Process-local Entity Identities

The Mod SHALL expose a stable, process-local instance ID for each current combat
hand card and enemy, in addition to existing index fields.

#### Scenario: Two identical cards occupy the hand

- **GIVEN** two hand cards have the same `card_id` and display properties
- **WHEN** the Mod returns combat state
- **THEN** each card has a distinct `card_instance_id`
- **AND** each ID stays associated with its live card object while that object
  remains in the running game process

#### Scenario: An entity leaves the current combat state

- **GIVEN** a card is exhausted or an enemy dies
- **WHEN** the Runtime later tries to resolve that entity ID from current state
- **THEN** the entity is absent
- **AND** the Runtime does not substitute a different index or a same-name entity

### Requirement: play_card Accepts Stable Instance References

The Mod SHALL accept optional `card_instance_id` and `target_instance_id` for
`play_card`, while retaining index-only requests for older clients.

#### Scenario: A request names a current hand card by instance ID

- **GIVEN** a `play_card` request has a current `card_instance_id`
- **WHEN** the Mod executes the request
- **THEN** it resolves the current live hand card by that ID
- **AND** it does not depend on the request's prior `card_index`

#### Scenario: A request references a stale entity

- **GIVEN** a `play_card` request names a card or target ID absent from current
  combat state
- **WHEN** the Mod validates the request
- **THEN** it returns a structured stale-instance error
- **AND** it does not execute a different card or target

### Requirement: Runtime Revalidates Each Planned Action

Runtime SHALL use stable instance IDs for a multi-action combat plan and SHALL
revalidate the next action after every completed action.

#### Scenario: Indexes change after an earlier card is played

- **GIVEN** a plan contains more than one card action
- **AND** the first action changes card positions
- **WHEN** Runtime evaluates the next action against fresh state
- **THEN** it resolves the intended card by `card_instance_id`
- **AND** it either executes that specific card or stops the remaining plan
- **AND** it never applies an index arithmetic correction

