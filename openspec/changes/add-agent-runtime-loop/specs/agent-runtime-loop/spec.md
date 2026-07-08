# Delta for Agent Runtime Loop

## ADDED Requirements

### Requirement: Runtime 使用正式游戏启动和健康检查

Runtime SHALL 在 live run 开始前确认游戏通过受支持方式启动，并确认 STS2AIAgent bridge 可用。

#### Scenario: Steam 启动后 health check 成功

- **WHEN** Runtime 准备开始 live run
- **THEN** 它调用配置好的 health endpoint 或 MCP `health_check`
- **AND** 它记录 `game_version`、`mod_version`、`protocol_version` 和 bridge source
- **AND** 它把 Steam 正式启动作为 macOS/Steam 的推荐启动方式

#### Scenario: 游戏桥接不可用

- **GIVEN** health check 无法连接或返回非 ready 状态
- **WHEN** Runtime 初始化 live run
- **THEN** Runtime 不进入 gameplay loop
- **AND** Runtime 记录 bridge unavailable error

### Requirement: Runtime 拥有 Agent 主循环

Runtime SHALL 负责一局 run 的主循环，包括读取状态、构建 `GameStateSnapshot`、获取 `KnowledgeContext`、选择 Policy、验证动作、执行动作、等待动作结果稳定、重新读取状态、写入 `StepRecord`。

#### Scenario: Runtime 执行一个正常 decision step

- **GIVEN** `GameClient.health` 成功
- **AND** `GameClient.get_state` 返回 actionable state
- **WHEN** Runtime 执行一个 decision step
- **THEN** Runtime 构建 `GameStateSnapshot`
- **AND** Runtime 调用 `KnowledgeProvider.for_state`
- **AND** Runtime 通过 `ScreenRouter` 选择对应 Policy
- **AND** Runtime 调用 `Policy.decide`
- **AND** Runtime 验证 `PolicyDecision.action`
- **AND** Runtime 通过 `GameClient.act` 执行动作
- **AND** Runtime 等待动作完成，直到游戏返回新的 actionable state 或 timeout
- **AND** Runtime 重新读取或接收动作后的最新 state
- **AND** Runtime append 一个 `StepRecord`

### Requirement: Runtime 每次决策前提供 Fresh Snapshot

Runtime SHALL 在每次调用 Policy 前提供 fresh `GameStateSnapshot`，并防止 Policy 使用 stale indexes。

#### Scenario: 出牌后手牌 index 刷新

- **GIVEN** Runtime 已执行 `play_card`
- **WHEN** Runtime 需要下一次决策
- **THEN** Runtime 重新读取或等待 fresh state
- **AND** Policy 必须根据最新 `combat.hand[].index` 重新选择 `card_index`

#### Scenario: Action response 的 state 不足以继续决策

- **GIVEN** `GameClient.act` 返回了 state
- **AND** 该 state 暂时缺少当前 screen 的普通决策动作
- **WHEN** Runtime 需要继续 gameplay loop
- **THEN** Runtime 调用 `get_state` 或 `wait_until_actionable`
- **AND** Runtime 不把该 immediate state 直接交给 Policy 做下一次普通决策

### Requirement: Runtime 等待动作完成后的 Actionable State

Runtime SHALL 在每次执行动作后等待游戏状态稳定，避免基于动画、结算、loading 或旧回合状态继续决策。

#### Scenario: play_card 后 action window 暂时关闭

- **GIVEN** Runtime 已通过 `GameClient.act` 执行 `play_card`
- **AND** 返回 state 中暂时只有 `save_and_quit`、`use_potion` 或 `discard_potion` 等 passive/side actions
- **WHEN** Runtime 需要继续战斗决策
- **THEN** Runtime 等待 fresh state 恢复 `play_card` 或 `end_turn`
- **AND** Runtime 在 timeout 前不请求 CombatPolicy 做普通出牌决策

#### Scenario: end_turn 后 immediate state 仍是旧回合

- **GIVEN** Runtime 已通过 `GameClient.act` 执行 `end_turn`
- **WHEN** action response 返回旧 turn、旧 hand 或未结算 HP
- **THEN** Runtime 继续等待 fresh actionable state
- **AND** Runtime 使用等待后的最新 turn、HP、hand 和 intent 继续决策

### Requirement: ScreenRouter 覆盖 MVP0 游戏场景

Runtime SHALL 根据 `GameStateSnapshot.screen` 和 overlay 状态把决策路由给对应 Policy，并支持所有 MVP0 必需 screen。

#### Scenario: Runtime 路由战斗决策

- **GIVEN** `GameStateSnapshot.screen` 是 `COMBAT`
- **AND** combat action window 是 actionable
- **WHEN** Runtime 需要决策
- **THEN** 它调用 `CombatPolicy.decide`

#### Scenario: Runtime 路由地图决策

- **GIVEN** `GameStateSnapshot.screen` 是 `MAP`
- **WHEN** Runtime 需要选择下一个节点
- **THEN** 它调用 `MapPolicy.decide`
- **AND** Policy 返回 `choose_map_node` 类 `AgentAction`

#### Scenario: Runtime 路由奖励决策

- **GIVEN** `GameStateSnapshot.screen` 是 `REWARD`
- **WHEN** Runtime 需要领取、选牌、跳过或继续
- **THEN** 它调用 `RewardPolicy.decide`

#### Scenario: Overlay 优先于底层房间

- **GIVEN** 当前 screen 是 `CARD_SELECTION` 或 `MODAL`
- **WHEN** Runtime 需要决策
- **THEN** Runtime 先调用 `SelectionPolicy` 或 `ModalPolicy`
- **AND** Runtime 不继续调用底层 room policy，直到 overlay 被解决

#### Scenario: 未实现 screen 安全停止

- **GIVEN** Runtime 遇到已知但未实现的 screen
- **WHEN** 没有对应 Policy 可以处理
- **THEN** Runtime 返回 `needs_human` 或安全停止
- **AND** Runtime 写入 `StepRecord` / `RunSummary` 说明原因

### Requirement: Runtime 覆盖 MVP0 控制动作

Runtime SHALL 支持 MVP0 所需的通用 `AgentAction.action` 名称，并统一通过 `GameClient.act` 执行。

#### Scenario: Combat action 覆盖出牌、结束回合和药水

- **GIVEN** 当前 screen 是 `COMBAT`
- **WHEN** Policy 需要行动
- **THEN** 它可以返回 `play_card`、`end_turn`、`use_potion` 或 `discard_potion`
- **AND** Runtime 根据最新 snapshot 验证 card、target 和 potion indexes

#### Scenario: Map action 覆盖选节点和地图药水动作

- **GIVEN** 当前 screen 是 `MAP`
- **WHEN** Policy 选择地图节点或处理可用药水动作
- **THEN** 它可以返回 `choose_map_node`、`use_potion` 或 `discard_potion`
- **AND** Runtime 根据最新 `map.available_nodes` 或 `run.potions` 验证 index

#### Scenario: Reward action 覆盖奖励处理

- **GIVEN** 当前 screen 是 `REWARD`
- **WHEN** Policy 处理奖励
- **THEN** 它可以返回 `claim_reward`、`choose_reward_card`、`skip_reward_cards`、`collect_rewards_and_proceed` 或 `resolve_rewards`
- **AND** Runtime 根据最新 reward payload 验证 index 和可用动作

### Requirement: Runtime 执行动作前验证 AgentAction

Runtime SHALL validate Policy actions before calling the live game.

#### Scenario: Unavailable action 被拒绝

- **GIVEN** Policy 返回一个 `AgentAction`
- **AND** 该 action 不在 `GameStateSnapshot.available_actions`
- **WHEN** Runtime 验证该 decision
- **THEN** Runtime 拒绝该 action
- **AND** Runtime 记录 validation error
- **AND** Runtime 不调用 live game API

#### Scenario: Card target 以最新 hand payload 为准

- **GIVEN** Policy 返回 `action = "play_card"`
- **AND** selected hand card 的 `requires_target = true`
- **WHEN** Runtime 验证该 action
- **THEN** Runtime 要求 `target_index` 存在于 selected card 的 `valid_target_indices`
- **AND** Runtime 不依赖 `actions/available` 中对 `play_card` 的粗粒度 target 描述

#### Scenario: Potion index 以最新 run.potions 为准

- **GIVEN** Policy 返回 `use_potion` 或 `discard_potion`
- **WHEN** Runtime 验证该 action
- **THEN** Runtime 确认 `potion_index` 对应最新 `run.potions` 中的 occupied potion
- **AND** Runtime 确认该 potion 满足 `can_use` 或 `can_discard`

### Requirement: Runtime 只重试 transient operations

Runtime SHALL 对读状态和等待类 transient operation 做有限重试，但 SHALL NOT 盲目重试可能已经生效的 game action。

#### Scenario: get_state 暂时失败

- **GIVEN** `GameClient.get_state` 因临时连接或过渡状态失败
- **WHEN** Runtime 处理该错误
- **THEN** Runtime 可以按 timeout/backoff 重试
- **AND** Runtime 在超过阈值后停止 run 并记录错误

#### Scenario: act timeout 后不重复执行动作

- **GIVEN** Runtime 调用 `GameClient.act`
- **AND** 请求 timeout 或连接中断
- **WHEN** Runtime 处理该错误
- **THEN** Runtime 先调用 `GameClient.get_state` 获取最新状态
- **AND** Runtime 不直接重复发送同一个 `AgentAction`
- **AND** Runtime 记录 recoverable 或 fatal error

### Requirement: Runtime 记录错误但 Policy 不负责系统诊断

Runtime SHALL 记录运行错误、最近状态和最近动作；gameplay Policy SHALL NOT 负责读取游戏日志或调试 Mod。

#### Scenario: Runtime 捕获 live bridge 错误

- **GIVEN** live bridge 断开、返回异常或持续 timeout
- **WHEN** Runtime 记录错误
- **THEN** 它写入 error code、exception summary、last screen、last available actions、last action request 和 last state summary
- **AND** Evaluation 或开发者可以事后分析这些记录
- **AND** Policy 不读取本地游戏日志来修复系统问题

### Requirement: Future Multi-Agent 复用同一套 Runtime Contract

Runtime SHALL 支持未来把具体 Policy 替换成 multi-agent 实现，但 SHALL 保持 live game I/O、validation、retry、wait 和 logging 仍由 Runtime 拥有。

#### Scenario: Combat 由独立 agent 处理

- **GIVEN** 当前 screen 是 `COMBAT`
- **WHEN** Runtime 把决策交给 Combat agent
- **THEN** handoff payload 包含 `GameStateSnapshot` 和 `KnowledgeContext`
- **AND** Combat agent 返回 `PolicyDecision`
- **AND** Runtime 仍然负责 action validation 和 game I/O
