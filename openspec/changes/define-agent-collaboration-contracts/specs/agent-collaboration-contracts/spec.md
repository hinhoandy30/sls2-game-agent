# Delta for Agent Collaboration Contracts

## ADDED Requirements

### Requirement: Runtime Owns Game I/O

Runtime SHALL be the only module that calls the live STS2 HTTP or MCP action
surface.

#### Scenario: Policy requests a legal action

- **GIVEN** Runtime has produced a fresh `GameStateSnapshot`
- **AND** Policy has returned an `AgentAction`
- **WHEN** Runtime receives the action
- **THEN** Runtime validates that `AgentAction.action` appears in
  `GameStateSnapshot.available_actions`
- **AND** Runtime sends the action to the game only after validation passes

### Requirement: GameStateSnapshot Contract

Runtime SHALL hand Policy a normalized `GameStateSnapshot` before every
decision.

#### Scenario: Snapshot contains routing data

- **WHEN** Runtime creates `GameStateSnapshot`
- **THEN** it includes `schema_version`, `source`, `observed_at`, `run_id`,
  `screen`, `session`, `turn`, `available_actions`, and `state`
- **AND** `state` contains the compact guided state payload for the current
  screen

### Requirement: AgentAction Contract

Policy SHALL express game-control intent with one `AgentAction`.

#### Scenario: Combat card action

- **GIVEN** the latest state exposes `play_card` as available
- **WHEN** Policy chooses a card
- **THEN** the `AgentAction` includes `action = "play_card"` and `card_index`
- **AND** it includes `target_index` only when the latest hand card marks a target
  as required

### Requirement: PolicyDecision Contract

Policy SHALL return a `PolicyDecision` object rather than executing game actions
itself.

#### Scenario: Policy can act, wait, or stop

- **WHEN** Policy finishes evaluating a state
- **THEN** it returns a decision with type `action`, `wait`, `stop`, or
  `needs_human`
- **AND** `action` decisions contain exactly one `AgentAction`

### Requirement: Knowledge Uses Live IDs

Knowledge retrieval SHALL be keyed from stable IDs present in the latest live
state.

#### Scenario: Combat knowledge retrieval

- **GIVEN** `GameStateSnapshot.screen` is `COMBAT`
- **AND** the state contains enemy IDs and hand card IDs
- **WHEN** Runtime builds context for Policy
- **THEN** Knowledge returns compact entries for the current enemy IDs and card
  IDs
- **AND** Knowledge includes source references for returned entries

### Requirement: Evaluation Consumes Trajectories

Evaluation SHALL consume append-only trajectory records and run summaries instead
of live game APIs.

#### Scenario: Runtime records an attempted action

- **WHEN** Runtime attempts any game action
- **THEN** Runtime appends one `StepRecord`
- **AND** the record includes state summary, knowledge references, decision,
  action request, action result, and error information

### Requirement: Fixtures Unblock Parallel Work

The project SHALL maintain representative state fixtures so teams can build
before live integration is complete.

#### Scenario: Policy tests with fixtures

- **GIVEN** a fixture for `COMBAT`, `MAP`, or `REWARD`
- **WHEN** a Policy module is tested
- **THEN** the test can call `Policy.decide` with fixture state and expected
  knowledge
- **AND** it can assert the returned `PolicyDecision` without launching the game

### Requirement: Module Boundaries Stay Independent

Runtime, Policy, Knowledge, Evaluation, and Mod/API work SHALL stay independently
testable through shared contracts.

#### Scenario: Teams work in parallel

- **GIVEN** this specification is accepted
- **WHEN** teams implement their modules
- **THEN** Runtime, Policy, Knowledge, Evaluation, and Mod/API work can proceed
  against shared contracts without requiring a live game for every task

