# Spec Delta: Agent Collaboration Contracts

## ADDED Requirements

### Requirement: Runtime Owns Game I/O

Runtime SHALL be the only module allowed to call the live STS2 HTTP/MCP action
surface. Policy, Knowledge, and Evaluation SHALL operate through shared data
contracts.

### Requirement: Policy Returns AgentAction

Policy modules SHALL return `PolicyDecision` objects. Game-control decisions
SHALL contain exactly one `AgentAction` object.

### Requirement: Knowledge Uses Live IDs

Knowledge retrieval SHALL be keyed from IDs present in the latest live state,
such as `card_id`, `enemy_id`, `relic_id`, `potion_id`, and `event_id`.

### Requirement: Evaluation Consumes Trajectories

Evaluation SHALL consume append-only `StepRecord` JSONL files and `RunSummary`
objects. Evaluation SHALL NOT require a live game process.

### Requirement: Fixtures Unblock Parallel Work

The project SHALL maintain representative state fixtures so Policy, Knowledge,
and Evaluation can build and test before Runtime is fully integrated.

