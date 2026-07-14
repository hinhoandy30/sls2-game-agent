# Proposal: 专项 Agent 编排与复盘经验闭环

## Why

现有 Runtime 可以执行单个 LLM Policy，但路线、战斗、卡组发展和失败复盘共享的信息边界
尚未形成产品级闭环。将所有 screen 交给一个泛化 prompt 会使卡组长期目标丢失，也难以从失败中
积累可追溯经验。

## What Changes

- 增加确定性的 `AgentOrchestrator`：按 screen 调用 RouteStrategy、Combat 或
  RunDevelopment 专项 agent；它不调用 LLM 做路由，也不直接操作游戏。
- 增加 Pydantic `DeckAssessment`、`StrategicPlan`、`ExperienceLesson` 与运行内
  `RunContextStore`。
- RouteStrategyAgent 同时负责长期路线偏好和当前地图节点；CombatAgent 负责战斗；
  RunDevelopmentAgent 负责奖励、选牌、事件、商店、休息和宝箱。
- 在 run 失败后调用 RunReviewAgent，读取 trajectory/segment/context，生成带证据的经验条目，
  写入 `agent_knowledge/experience/v1/`，并在后续匹配状态中作为明确标记为“历史经验”的上下文。
- 在 trajectory / summary 中记录 agent、deck signature、战略计划版本、复盘产物及 LLM usage。

## Non-goals

- 不在本 change 中承诺高胜率、全卡牌评价或全事件策略。
- 不让任何 Policy/Review agent 直接调用 MCP、HTTP 或修改游戏。
- 不允许复盘模型把推测写入 `data/knowledge/v1/` 的游戏事实库。
