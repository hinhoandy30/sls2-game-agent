# Delta for Combat Policy

## ADDED Requirements

### Requirement: Combat Policy Returns Decisions

CombatPolicyV0 SHALL return `PolicyDecision` objects and SHALL NOT call the live
game API.

#### Scenario: Playable attack exists

- **GIVEN** a combat fixture with a playable attack
- **WHEN** CombatPolicyV0 decides
- **THEN** it returns an `action` decision with a legal `AgentAction`

### Requirement: Combat Policy Avoids Illegal Targets

CombatPolicyV0 SHALL use target indexes only when the latest state marks them as
valid.

#### Scenario: Card requires enemy target

- **GIVEN** a playable card with `target = "enemies"`
- **AND** `targets` contains `[0]`
- **WHEN** CombatPolicyV0 chooses that card
- **THEN** the returned `AgentAction` includes `target_index = 0`

### Requirement: Combat Policy Ends Turn Deliberately

CombatPolicyV0 SHALL end turn only when no better legal combat action is
available under its MVP0 heuristics.

#### Scenario: No useful playable cards remain

- **GIVEN** a combat fixture with `end_turn` available
- **AND** no playable card improves the position under V0 heuristics
- **WHEN** CombatPolicyV0 decides
- **THEN** it returns `action = "end_turn"`

