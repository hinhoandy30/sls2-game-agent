# Delta for Specialist Strategy Configuration

## ADDED Requirements

### Requirement: Specialist Strategy Is a Versioned External Artifact

The Runtime SHALL load each specialist Agent instruction from a versioned, validated strategy file rather than an
inline orchestration-code prompt string.

#### Scenario: Combat strategy loads successfully

- **GIVEN** the default strategy directory contains a valid `combat.json`
- **WHEN** `AgentOrchestrator` initializes
- **THEN** CombatAgent receives the rendered Chinese rules from that file
- **AND** no combat tactical rule is required to be hard-coded in the orchestrator.

#### Scenario: Invalid strategy fails clearly

- **GIVEN** a strategy file is missing, malformed, or declares another agent name
- **WHEN** the corresponding specialist Agent initializes
- **THEN** initialization fails with a path-specific configuration error
- **AND** it does not silently use an inline fallback strategy.

### Requirement: Trajectories Identify the Strategy Version

Every decision made by a specialist Agent SHALL include strategy identity metadata.

#### Scenario: Strategy metadata is recorded

- **WHEN** CombatAgent produces a decision
- **THEN** `decision.metadata.agent.strategy` includes `strategy_id`, `strategy_revision`, and `strategy_hash`
- **AND** Evaluation can use those fields to distinguish trajectories.
