# Proposal: Define Agent Collaboration Contracts

## Why

The team needs to build a dedicated STS2 agent runner without depending on
Codex skills at runtime. Multiple groups need to work in parallel, but they need
stable contracts for state, actions, knowledge, logs, and evaluation.

Without these contracts, Runtime work blocks Evaluation, Policy work depends on
live game access, and knowledge usage risks becoming ad-hoc prompt stuffing.

## What Changes

- Add an OpenSpec-style contract store under `openspec/`.
- Define stable schemas for:
  - `GameStateSnapshot`
  - `AgentAction`
  - `PolicyDecision`
  - `KnowledgeContext`
  - `StepRecord`
  - `RunSummary`
- Define module boundaries for Runtime, Policy, Knowledge, Evaluation, and
  Mod/API maintenance.
- Define the first fixture set that lets teams work before full runtime
  integration.

## Impact

- Runtime can expose a small, testable interface over the existing MCP/HTTP API.
- Policy can develop against fixtures.
- Knowledge can build retrieval by stable IDs.
- Evaluation can build reports from JSONL trajectories before live runs exist.
- Future multi-agent work can reuse the same handoff-shaped contracts.

