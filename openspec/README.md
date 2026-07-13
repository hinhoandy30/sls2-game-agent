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

## Current Implementation Status

- `implementation-status.md`
  - 团队当前可以依赖的 Runtime 能力、最近实现记录、日志产物和明确未完成项。
  - 开始 Policy、Knowledge 或 Evaluation 工作前先读这一页；它避免把设计目标误认为已经可用的功能。

## Current Changes

- `changes/define-agent-collaboration-contracts/`
  - Initial change proposal that introduced the shared contracts.
- `changes/define-mvp0-shared-contract-schemas/`
  - MVP0 具体字段契约，覆盖 `GameClient`、`GameStateSnapshot`、`AgentAction`、
    `PolicyDecision`、`KnowledgeContext`、`StepRecord`、fixtures 和 `RunSummary`。
- `changes/add-agent-runtime-loop/`
  - 专用 Runtime 主循环、Pydantic `ActionSpec`、即时模式启动和 LLM 动作计划的实现记录。
- `changes/add-trajectory-logging/`
  - append-only 轨迹、分支 segment、运行时间和 token 统计的实现记录。
- `changes/add-stable-combat-action-identities/`
  - combat 卡牌/敌人稳定实例 ID，以及多步计划在 fresh state 中重新定位实体的跨端改动。
- `changes/enable-stable-combat-planning/`
  - LLM combat 默认一次规划多张稳定实体动作、Runtime 逐步执行与安全重规划的改动。

## Workflow

1. Discuss unclear work in chat or a short exploration note.
2. Create or update a change under `openspec/changes/<change-id>/`.
3. Review `proposal.md`, spec deltas, `design.md`, and `tasks.md` before code.
4. Build against the accepted contracts.
5. Archive completed changes once implementation and verification are done.
