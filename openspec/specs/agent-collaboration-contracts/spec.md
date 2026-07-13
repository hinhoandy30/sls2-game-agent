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
- **THEN** the `AgentAction` includes `action = "play_card"` and the current
  `card_instance_id` when the bridge exposes one
- **AND** it includes `target_instance_id` for an enemy target when the bridge
  exposes one
- **AND** Runtime resolves the current indexes from the fresh state before
  execution
- **AND** index-only requests remain the compatibility fallback for older bridge
  versions

#### Scenario: Option-index action

- **GIVEN** the latest state exposes a map, reward, shop, event, rest, timeline,
  character-select, or selection action
- **WHEN** Policy chooses an option
- **THEN** the `AgentAction` includes `option_index` from the latest state
- **AND** Runtime rejects option indexes that are absent from the current payload

### Requirement: Runtime Provides A Derived Legal Action View

Runtime SHALL derive a `legal_actions` view from the latest snapshot before an
LLM Policy decides. This is a runtime-derived compatibility layer in MVP0; it is
not yet a native C# Mod/API field.

#### Scenario: LLM selects a concrete legal action

- **GIVEN** the latest snapshot contains `available_actions` and the current
  screen payload
- **WHEN** Runtime prepares an LLM prompt
- **THEN** it provides concrete legal action entries with an `id`, action name,
  and any required card, target, potion, or option index
- **AND** the LLM MAY return one `legal_action_id` instead of inventing indexes
- **AND** Runtime resolves that ID against the same snapshot before it calls the
  live game

#### Scenario: A legal action becomes stale

- **GIVEN** a previous card play, kill, draw, or screen transition changed the
  current state
- **WHEN** Runtime validates a later action
- **THEN** it rebuilds `legal_actions` from the fresh snapshot
- **AND** it rejects an unavailable `legal_action_id` without calling the game

### Requirement: Multi-action Plans Remain Conservative

Runtime MAY execute a short action plan, but SHALL validate each member against
the latest state and stop the remaining plan when it becomes unsafe to continue.

#### Scenario: A combat action changes hand indexes

- **GIVEN** an LLM returned more than one combat action
- **WHEN** one action is executed
- **THEN** Runtime reads or waits for a fresh actionable state before the next
  action
- **AND** it validates the next action again
- **AND** it stops the rest of the plan on stale indexes, invalid targets, or a
  screen change

#### Scenario: A combat plan uses stable entity IDs

- **GIVEN** the current bridge exposes `card_instance_id` and
  `enemy_instance_id`
- **WHEN** an LLM creates a combat action plan
- **THEN** each combat card action SHALL be selected through a
  `legal_action_id` that resolves to those entity IDs
- **AND** Runtime SHALL not correct hand indexes with index arithmetic
- **AND** a missing card or target ID stops the remaining plan without playing a
  different entity

#### Scenario: Stable combat planning is unavailable

- **GIVEN** the bridge omits a required combat card or enemy instance ID
- **WHEN** Runtime prepares the LLM decision prompt
- **THEN** it falls back to the single-action contract
- **AND** it records the fallback reason in `PolicyDecision.metadata`

#### Scenario: Policy needs reliable tactical sequencing

- **GIVEN** a policy needs to guarantee a sequence after draws or enemy deaths
- **WHEN** the team implements that policy
- **THEN** it SHALL use a future tactical solver or make one decision per fresh
  state
- **AND** it SHALL NOT assume MVP0 raw-index action plans are stable

### Requirement: PolicyDecision Contract

Policy SHALL return a `PolicyDecision` object rather than executing game actions
itself. The normal MVP0 form contains one `AgentAction`; the explicitly enabled
experimental combat-plan form also contains a bounded `action_plan` whose first
member remains `PolicyDecision.action` for backwards compatibility.

#### Scenario: Policy can act, wait, or stop

- **WHEN** Policy finishes evaluating a state
- **THEN** it returns a decision with type `action`, `wait`, `stop`, or
  `needs_human`
- **AND** normal `action` decisions contain one `AgentAction`
- **AND** an explicitly enabled experimental combat plan contains a bounded
  ordered `action_plan` and is subject to Runtime revalidation after every member
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

### Requirement: Trajectories Preserve Checkpoint Branches And Telemetry

Runtime SHALL record enough information to distinguish a continued timeline
from a checkpoint retry, and SHALL include runtime cost telemetry when it is
available.

#### Scenario: continue_run returns a different checkpoint state

- **GIVEN** Runtime executes `continue_run` in the same runtime process
- **WHEN** the state hash after the action differs from the prior state hash
- **THEN** Runtime appends a new `TrajectorySegment` with
  `start_reason = "retry_from_checkpoint"`
- **AND** the segment includes a parent segment ID, checkpoint hash, start floor,
  screen, and HP
- **AND** subsequent `StepRecord` entries carry that segment ID

#### Scenario: Runtime writes an LLM-backed run summary

- **WHEN** a run ends or stops
- **THEN** `RunSummary` includes elapsed `duration_seconds` and `segment_count`
- **AND** it includes aggregated token usage when the configured LLM provider
  returned usage metadata
- **AND** a missing provider usage field does not prevent the summary from being
  written

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
