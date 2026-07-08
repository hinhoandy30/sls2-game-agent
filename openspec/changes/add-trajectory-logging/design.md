# Design: Trajectory Logging

## Output Shape

Runtime writes:

```text
runs/<date>/<run-id>/
  trajectory.jsonl
  summary.json
  summary.md
```

## StepRecord

Each JSONL line should include:

- schema version
- run id
- step id
- timestamp
- repo commit
- game version
- screen and floor
- state summary
- knowledge references
- policy decision
- action request
- action result
- metrics delta
- error, if any

## RunSummary

The summary should include:

- seed
- character
- ascension
- start/end time
- final result
- floor reached
- invalid action count
- recoverable error count
- terminal reason

## Privacy and Size

Logs should avoid full raw state by default. Store compact state summaries and
IDs; capture raw payloads only when debug logging is explicitly enabled.

