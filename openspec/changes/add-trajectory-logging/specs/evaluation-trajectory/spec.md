# Delta for Evaluation Trajectory

## ADDED Requirements

### Requirement: Runtime Records StepRecord

Runtime SHALL append one `StepRecord` for every attempted game action.

#### Scenario: Successful action is recorded

- **WHEN** Runtime executes an action successfully
- **THEN** it appends a `StepRecord`
- **AND** the record includes state summary, decision, action request, action
  result, and next screen

#### Scenario: Rejected action is recorded

- **GIVEN** Runtime rejects a Policy action during validation
- **WHEN** the rejection happens
- **THEN** Runtime appends a `StepRecord`
- **AND** the record includes the validation error

### Requirement: Evaluation Reads Trajectory Files

Evaluation SHALL compute metrics from `trajectory.jsonl` without a live game.

#### Scenario: Metrics from fixture trajectory

- **GIVEN** a fixture `trajectory.jsonl`
- **WHEN** Evaluation reads it
- **THEN** it reports invalid actions, recoverable errors, final screen, and
  floor reached

### Requirement: Runtime Writes RunSummary

Runtime SHALL write one `RunSummary` for each run.

#### Scenario: Run ends or stops

- **WHEN** a run reaches victory, defeat, manual stop, or unrecoverable error
- **THEN** Runtime writes a summary with result, floor reached, and terminal
  reason

