# STS2 Agent OpenSpec Store

This directory is the team contract store for the dedicated STS2 agent project.
It follows the OpenSpec-style workflow: write the intended behavior and shared
interfaces before implementation, then let each team build against the same
contract.

## How We Use It

- Stable contracts live under `openspec/specs/`.
- Proposed changes live under `openspec/changes/<change-id>/`.
- A change should include `proposal.md`, `design.md`, `tasks.md`, and one or
  more spec deltas under `specs/`.
- Runtime, Policy, Knowledge, and Evaluation work can proceed in parallel once
  the contract fields in `agent-collaboration-contracts` are agreed.

## Current Baseline

- `specs/agent-collaboration-contracts/spec.md`: shared module boundaries,
  data contracts, and handoff rules for the first dedicated agent runner.
- `changes/define-agent-collaboration-contracts/`: initial proposal and rollout
  checklist for adopting these contracts.

