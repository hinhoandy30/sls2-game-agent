# Proposal: 添加 Agent Runtime Loop

## 为什么

项目需要一个专用 runner 来驱动 STS2，而不是依赖 Codex skill、手工 curl 或临时脚本。Runtime 必须拥有 live game I/O，并向 Policy、Knowledge、Evaluation 提供稳定的状态、动作、日志边界。

本 change 基于已经验证过的本地实机行为：

- Steam 正式启动后，Mod API 可以稳定暴露 `http://127.0.0.1:8080/`。
- 直接打开 `.app` 会触发 Steamworks 初始化失败：`No appID found`，因此 Runtime 文档和启动工具必须把 Steam 启动作为正式路径。
- `/state` 返回 `data.agent_view` 和完整 payload，可作为 normalized snapshot 的输入。
- `/action` 返回 `status=completed` 和 `stable=true` 时，返回的 immediate state 仍可能暂时缺少 `play_card` / `end_turn`。
- `end_turn` 的 immediate state 可能仍处于旧回合，必须等待 fresh actionable state 后才能继续决策。
- `actions/available` 只能说明动作是否可用；`play_card` 是否需要目标必须以最新 `combat.hand[].requires_target` 和 `valid_target_indices` 为准。
- `MAP` 也可能暴露 `use_potion` / `discard_potion`，药水动作不应硬编码为 combat-only。

## 改什么

- 定义 Runtime 主循环：health -> state -> normalize -> knowledge -> route -> policy -> validate -> act -> wait/fresh state -> log。
- 定义 `GameClient` 边界，把 MCP guided tools 或 HTTP API 藏在同一个 adapter 后面。
- 定义 `ScreenRouter`：按 `screen` 和 overlay 状态路由到对应 Policy。
- 定义动作后等待机制：不能直接相信 action response 里的 immediate state 可以用于下一次决策。
- 定义 Runtime action validation：使用最新 state 验证 action、card index、target index、option index、potion index。
- 定义有限重试机制：只重试 transient read/wait 操作，不盲目重试可能已经生效的 act。
- 定义错误记录边界：Runtime 记录错误和上下文，Evaluation/开发者分析日志；游戏 Policy 不负责调试系统。
- 为未来 multi-agent 留出接口，但 MVP0 仍使用单进程、可测试的 Policy 插槽。

## 影响

- Runtime 组可以开始写专用 agent 骨架。
- Policy 组只实现 `Policy.decide`，不碰 live game API。
- Knowledge 组只根据最新 snapshot 的 ID 返回紧凑上下文。
- Evaluation 组可以消费 Runtime 产生的 `StepRecord` / `RunSummary`。
- 后续 multi-agent 可以复用同一套 `GameStateSnapshot`、`KnowledgeContext`、`PolicyDecision` handoff payload。
