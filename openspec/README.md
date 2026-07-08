# STS2 Agent OpenSpec

This directory follows the official Fission-AI/OpenSpec shape:

```text
openspec/
  project.md
  AGENTS.md
  config.yaml
  specs/
  changes/
```

Use it as the team-facing source of truth for the dedicated STS2 agent runner.

## Current Spec

- `specs/agent-collaboration-contracts/spec.md`
  - Current contract for Runtime, Policy, Knowledge, Evaluation, and Mod/API
    collaboration.

## Current Changes

- `changes/define-agent-collaboration-contracts/`
  - Initial change proposal that introduced the shared contracts.
- `changes/define-mvp0-shared-contract-schemas/`
  - MVP0 具体字段契约，覆盖 `GameClient`、`GameStateSnapshot`、`AgentAction`、
    `PolicyDecision`、`KnowledgeContext`、`StepRecord`、fixtures 和 `RunSummary`。

## Workflow

1. Discuss unclear work in chat or a short exploration note.
2. Create or update a change under `openspec/changes/<change-id>/`.
3. Review `proposal.md`, spec deltas, `design.md`, and `tasks.md` before code.
4. Build against the accepted contracts.
5. Archive completed changes once implementation and verification are done.
