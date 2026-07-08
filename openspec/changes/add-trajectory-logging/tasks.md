# Tasks: Add Trajectory Logging

## 1. Schemas

- [ ] Define `StepRecord`.
- [ ] Define `RunSummary`.
- [ ] Define compact `state_summary`.

## 2. Logger

- [ ] Implement append-only JSONL writer.
- [ ] Implement summary writer.
- [ ] Add run directory creation.
- [ ] Include repo commit and game version when available.

## 3. Evaluation Fixtures

- [ ] Add a mock first-combat trajectory.
- [ ] Add a failed-action trajectory.
- [ ] Add a completed-reward trajectory.

## 4. Verification

- [ ] Add parser tests for JSONL logs.
- [ ] Add summary metric tests.
- [ ] Run `openspec validate --all`.

