# Proposal: Add Trajectory Logging

## Why

Evaluation cannot develop independently unless every attempted action has a
stable, append-only record. MVP0 needs logs that explain what the agent saw,
what it decided, what it did, and what happened next.

## What Changes

**StepRecord JSONL**
- From: Run behavior is visible only in console output or ad-hoc notes.
- To: Runtime appends one structured `StepRecord` for each attempted action.
- Reason: Evaluation needs reproducible trajectories.
- Impact: Runtime writes logs; Evaluation can run without a live game.

**RunSummary**
- From: Final results are manually inferred.
- To: Each run produces a summary with seed, character, ascension, result, floor,
  errors, and metrics.
- Reason: Team needs comparable run outcomes.
- Impact: Enables MVP0 reports and regression checks.

## Impact

- Evaluation team can build metrics from fixtures immediately.
- Runtime team has a concrete logging contract.
- Policy decisions become reviewable after failed runs.

