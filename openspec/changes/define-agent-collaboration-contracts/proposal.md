# Proposal: Define Agent Collaboration Contracts

## Why

The team needs to build a dedicated STS2 agent runner without depending on
Codex skills at runtime. Multiple groups need to work in parallel, but they need
stable contracts for state, actions, knowledge, logs, and evaluation.

Without these contracts, Runtime work blocks Evaluation, Policy work depends on
live game access, and knowledge usage risks becoming ad-hoc prompt stuffing.

## What Changes

**OpenSpec project setup**
- From: No team-owned spec source of truth in this repository.
- To: `openspec/` contains official OpenSpec-style project context, config,
  current specs, and active changes.
- Reason: AI coding agents and teammates need a durable contract outside chat.
- Impact: Non-breaking; adds planning artifacts only.

**Agent collaboration contracts**
- From: Runtime, Policy, Knowledge, and Evaluation boundaries were described in
  chat but not encoded as reviewable contracts.
- To: `agent-collaboration-contracts` defines observable module boundaries and
  shared data contracts.
- Reason: Teams need to work in parallel without blocking on live Runtime.
- Impact: Non-breaking; future code should conform to these contracts.

**Trajectory and fixture contract**
- From: Evaluation would depend on ad-hoc logs or live game access.
- To: Evaluation consumes `StepRecord` JSONL and `RunSummary` objects, while
  Policy and Knowledge can test against fixtures.
- Reason: Evaluation and Policy should start before Runtime is fully complete.
- Impact: Non-breaking; establishes required logging behavior for future Runtime.

## Impact

- Runtime can expose a small, testable interface over the existing MCP/HTTP API.
- Policy can develop against fixtures.
- Knowledge can build retrieval by stable IDs.
- Evaluation can build reports from JSONL trajectories before live runs exist.
- Future multi-agent work can reuse the same handoff-shaped contracts.
