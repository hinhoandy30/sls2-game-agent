# Delta for Agent Runtime Loop

## ADDED Requirements

### Requirement: Runtime Initializes Game Session

Runtime SHALL verify the game bridge is reachable before attempting gameplay.

#### Scenario: Health check succeeds

- **WHEN** Runtime starts a live run
- **THEN** it calls the configured health endpoint or MCP `health_check`
- **AND** it records the detected game and Mod version

### Requirement: Runtime Produces Fresh Snapshots

Runtime SHALL produce a fresh `GameStateSnapshot` before each Policy decision.

#### Scenario: State is refreshed after action

- **GIVEN** Runtime has executed an `AgentAction`
- **WHEN** the action returns
- **THEN** Runtime uses the returned state or fetches a new state before asking
  Policy for another decision

### Requirement: Runtime Validates Actions

Runtime SHALL validate Policy actions before calling the live game.

#### Scenario: Unavailable action is rejected

- **GIVEN** Policy returns an `AgentAction`
- **AND** the action is absent from `GameStateSnapshot.available_actions`
- **WHEN** Runtime validates the decision
- **THEN** Runtime rejects the action
- **AND** records a validation error instead of calling the live game

### Requirement: Runtime Waits For Actionable State

Runtime SHALL tolerate short game transitions after actions.

#### Scenario: Action window is temporarily closed

- **GIVEN** the game returns a state with only passive actions available
- **WHEN** Runtime needs another decision
- **THEN** Runtime waits until an actionable state appears or a timeout occurs

