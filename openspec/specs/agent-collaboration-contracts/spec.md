# Agent Collaboration Contracts Specification

## Purpose

This specification defines the observable contracts that let the STS2 agent
team build a dedicated runner in parallel. It covers the boundaries between
Runtime, Policy, Knowledge, Evaluation, and Mod/API maintenance.

## Requirements

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

#### Scenario: Policy must not call the game

- **GIVEN** Policy is deciding a combat, reward, map, event, shop, or rest step
- **WHEN** Policy needs game information
- **THEN** Policy receives it through `GameStateSnapshot` and `KnowledgeContext`
- **AND** Policy does not call `/state`, `/action`, MCP `act`, or other live game
  APIs directly

### Requirement: GameStateSnapshot Contract

Runtime SHALL hand Policy a normalized `GameStateSnapshot` before every
decision.

#### Scenario: Snapshot contains routing data

- **WHEN** Runtime creates `GameStateSnapshot`
- **THEN** it includes `schema_version`, `source`, `observed_at`, `run_id`,
  `screen`, `session`, `turn`, `available_actions`, and `state`
- **AND** `state` contains the compact guided state payload for the current
  screen

#### Scenario: Snapshot prevents stale indexes

- **GIVEN** a previous decision used a card, map, reward, shop, event, rest, or
  selection index
- **WHEN** Runtime asks Policy for the next decision
- **THEN** Runtime provides a newly observed `GameStateSnapshot`
- **AND** Policy recomputes indexes from that snapshot

### Requirement: AgentAction Contract

Policy SHALL express game-control intent with one `AgentAction`.

#### Scenario: Combat card action

- **GIVEN** the latest state exposes `play_card` as available
- **WHEN** Policy chooses a card
- **THEN** the `AgentAction` includes `action = "play_card"` and `card_index`
- **AND** it includes `target_index` only when the latest hand card marks a target
  as required

#### Scenario: Option-index action

- **GIVEN** the latest state exposes a map, reward, shop, event, rest, timeline,
  character-select, or selection action
- **WHEN** Policy chooses an option
- **THEN** the `AgentAction` includes `option_index` from the latest state
- **AND** Runtime rejects option indexes that are absent from the current payload

### Requirement: PolicyDecision Contract

Policy SHALL return a `PolicyDecision` object rather than executing game actions
itself.

#### Scenario: Policy can act, wait, or stop

- **WHEN** Policy finishes evaluating a state
- **THEN** it returns a decision with type `action`, `wait`, `stop`, or
  `needs_human`
- **AND** `action` decisions contain exactly one `AgentAction`
- **AND** `wait`, `stop`, and `needs_human` decisions include a concise reason

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

#### Scenario: Knowledge does not stuff full docs

- **GIVEN** documentation and extracted game data are available locally
- **WHEN** Policy needs context for one decision
- **THEN** Knowledge returns a compact `KnowledgeContext`
- **AND** it does not load entire markdown indexes into the decision prompt by
  default

### Requirement: Evaluation Consumes Trajectories

Evaluation SHALL consume append-only trajectory records and run summaries instead
of live game APIs.

#### Scenario: Runtime records an attempted action

- **WHEN** Runtime attempts any game action
- **THEN** Runtime appends one `StepRecord`
- **AND** the record includes state summary, knowledge references, decision,
  action request, action result, and error information

#### Scenario: Evaluation runs before Runtime is complete

- **GIVEN** fixture trajectories exist
- **WHEN** Evaluation computes metrics
- **THEN** it reads `StepRecord` JSONL files and `RunSummary` objects
- **AND** it does not require a running STS2 process

### Requirement: Fixtures Unblock Parallel Work

The project SHALL maintain representative state fixtures so teams can build
before live integration is complete.

#### Scenario: Policy tests with fixtures

- **GIVEN** a fixture for `COMBAT`, `MAP`, or `REWARD`
- **WHEN** a Policy module is tested
- **THEN** the test can call `Policy.decide` with fixture state and expected
  knowledge
- **AND** it can assert the returned `PolicyDecision` without launching the game

#### Scenario: Evaluation tests with fixture runs

- **GIVEN** a fixture trajectory
- **WHEN** Evaluation computes metrics
- **THEN** it reports invalid actions, floor reached, terminal result, and
  recoverable errors from the fixture

### Requirement: Module Boundaries Stay Independent

Runtime, Policy, Knowledge, Evaluation, and Mod/API work SHALL stay independently
testable through shared contracts.

#### Scenario: Teams work in parallel

- **GIVEN** this specification is accepted
- **WHEN** teams implement their modules
- **THEN** Runtime builds `GameClient`, `ScreenRouter`, and run-loop behavior
- **AND** Policy builds decision functions against fixtures
- **AND** Knowledge builds retrieval by stable IDs
- **AND** Evaluation builds metrics from trajectory records
- **AND** Mod/API work fixes missing controls and state-contract defects found by
  other teams

