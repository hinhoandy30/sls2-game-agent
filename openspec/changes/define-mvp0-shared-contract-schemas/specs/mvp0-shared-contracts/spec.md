# Delta for MVP0 Shared Contracts

## ADDED Requirements

### Requirement: Runtime 拥有 GameClient 边界

Runtime SHALL 暴露 `GameClient` 作为 live game communication 边界，并且 SHALL 防止 Policy、Knowledge、Evaluation 直接调用真实 STS2 HTTP 或 MCP。

#### Scenario: Runtime 检查游戏桥接健康状态

- **WHEN** Runtime 启动一次 live run
- **THEN** 它调用 `GameClient.health`
- **AND** 它记录检测到的 game version、可用时的 Mod version，以及 bridge source

#### Scenario: Policy 不能调用 live game API

- **GIVEN** Policy 正在为任意 screen 做决策
- **WHEN** Policy 需要游戏信息
- **THEN** 它接收 `GameStateSnapshot` 和 `KnowledgeContext`
- **AND** 它不得直接调用 MCP tools、HTTP endpoints 或 `GameClient`

### Requirement: GameClient 支持 MVP0 操作

`GameClient` SHALL 支持 health checking、state reading、action execution，以及等待 actionable state。

#### Scenario: MVP0 runtime loop 调用 GameClient

- **WHEN** Runtime 执行一个 decision step
- **THEN** 它可以调用 `health`、`get_state`、`act` 和 `wait_until_actionable`
- **AND** 这些操作可以由 MCP guided tools 或等价 HTTP endpoints 支撑，但必须藏在同一个 interface 后面

### Requirement: GameStateSnapshot 使用 MVP0 Envelope

Runtime SHALL 向 Policy 和 Knowledge 提供 normalized `GameStateSnapshot`，并使用 `schema_version = "mvp0.v1"`。

#### Scenario: Snapshot 包含通用路由字段

- **WHEN** Runtime normalize live state
- **THEN** snapshot 包含 `schema_version`、`source`、`observed_at`、`run_id`、`game_version`、`screen`、`available_actions` 和 `state`
- **AND** `mod_version` 在已知时写入真实值，未知时设为 `unknown`

#### Scenario: Combat snapshot 包含决策字段

- **GIVEN** 当前 screen 是 `COMBAT`
- **WHEN** Runtime 构建 `GameStateSnapshot.state.combat`
- **THEN** 它包含 player HP 和 block、current energy、turn number、hand cards 和 enemies
- **AND** 每张 hand card 包含 `index`、`id`、`name`、`cost`、`playable`、`requires_target` 和 `valid_targets`
- **AND** 每个 enemy 包含 `index`、`id`、`name`、HP、block 和 best-known intent fields

### Requirement: AgentAction 表达一个标准化游戏请求

Policy SHALL 用且只用一个 `AgentAction` 表达一次 game-control request。

#### Scenario: Combat card action 是 index-safe 的

- **GIVEN** 最新的 `GameStateSnapshot.available_actions` 包含 `play_card`
- **AND** 被选择的 hand card 存在于最新 snapshot
- **WHEN** Policy 返回 card action
- **THEN** `AgentAction.action` 是 `play_card`
- **AND** `card_index` 等于最新 snapshot 中被选择卡牌的 index
- **AND** 只有被选择卡牌需要目标时才包含 `target_index`

#### Scenario: Option action 使用当前 option index

- **GIVEN** Policy 选择 map、reward、shop、event、rest、timeline、character-select 或 selection option
- **WHEN** 它返回 `AgentAction`
- **THEN** 它使用最新 snapshot 中的 `option_index`
- **AND** 如果 index 不存在或已经 stale，Runtime 拒绝该 action

### Requirement: Runtime 执行动作前验证 AgentAction

Runtime SHALL 在把 `AgentAction` 发送给游戏前，根据最新 `GameStateSnapshot` 验证它。

#### Scenario: Unavailable action 被拒绝

- **GIVEN** Policy 返回一个 `AgentAction`
- **AND** `AgentAction.action` 不在 `GameStateSnapshot.available_actions` 中
- **WHEN** Runtime 验证该 action
- **THEN** Runtime 拒绝它
- **AND** Runtime 在 `StepRecord` 中记录 validation error
- **AND** Runtime 不调用 live game action surface

#### Scenario: Stale combat index 被拒绝

- **GIVEN** Policy 返回 `action = "play_card"`
- **AND** `card_index` 不存在于最新 hand payload
- **WHEN** Runtime 验证该 action
- **THEN** Runtime 将它作为 stale 或 invalid action 拒绝

### Requirement: PolicyDecision 包装 AgentAction

Policy SHALL 返回 `PolicyDecision`，而不是直接调用游戏。

#### Scenario: Policy 返回 action decision

- **WHEN** Policy 决定行动
- **THEN** 它返回 `type = "action"`
- **AND** 它包含且只包含一个 `AgentAction`
- **AND** 它包含简短 `reason`

#### Scenario: Policy 返回 non-action decision

- **WHEN** Policy 当前不能或不应该立刻行动
- **THEN** 它返回 `type` 等于 `wait`、`stop` 或 `needs_human`
- **AND** 它包含简短 `reason`

### Requirement: KnowledgeContext 紧凑且由 ID 驱动

Knowledge SHALL 根据最新 `GameStateSnapshot` 中的 ID 返回 compact context。

#### Scenario: Combat knowledge 通过 ID 查询

- **GIVEN** combat snapshot 包含 hand card IDs 和 enemy IDs
- **WHEN** Runtime 请求 knowledge context
- **THEN** Knowledge 返回这些 ID 对应的 compact entries
- **AND** 每个返回事实包含 source reference
- **AND** 默认不包含完整 markdown documents

### Requirement: StepRecord 是 Evaluation 输入

Runtime SHALL 为每一次 attempted 或 rejected game action append 一个 `StepRecord`，并使用 `schema_version = "mvp0.v1"`。

#### Scenario: 成功动作记录

- **WHEN** Runtime 成功执行一个 action
- **THEN** 它 append 一个 `StepRecord`
- **AND** record 包含 `run_id`、`step_index`、`observed_at`、`screen_before`、`state_summary`、`knowledge_refs`、`decision`、`action_request`、`action_result` 和 `error`
- **AND** `error` 是 null

#### Scenario: 被拒绝动作记录

- **GIVEN** Runtime 在 validation 阶段拒绝一个 Policy action
- **WHEN** Runtime 记录该 step
- **THEN** `action_result.ok` 是 false
- **AND** `error` 描述 validation failure

### Requirement: RunSummary 描述一局游戏的终态

Runtime SHALL 在 run 结束、停止或 unrecoverable failure 时写入一个 `RunSummary`。

#### Scenario: 写入 run summary

- **WHEN** 一局游戏到达 victory、defeat、manual stop 或 unrecoverable error
- **THEN** Runtime 写入 summary，包含 `schema_version`、`run_id`、result、floor reached、terminal screen、terminal reason、step count 和 error count

### Requirement: Fixtures 覆盖 MVP0 Screens

项目 SHALL 维护脱敏后的 fixture states 和至少一个 fixture trajectory，以支持并行开发。

#### Scenario: MVP0 fixture set 存在

- **WHEN** 团队实现 MVP0 Runtime、Policy、Knowledge 或 Evaluation 工作
- **THEN** 存在 `MAIN_MENU`、`CHARACTER_SELECT`、`MAP`、`COMBAT` 和 `REWARD` 的 fixture states
- **AND** fixtures 不包含本地文件路径、Steam account IDs 或个人账号信息

#### Scenario: Evaluation 从 fixture trajectory 运行

- **GIVEN** 一个 fixture `trajectory.jsonl`
- **WHEN** Evaluation 计算 MVP0 metrics
- **THEN** 它不需要正在运行的 STS2 进程

### Requirement: Contract Changes 需要 OpenSpec Review

MVP0 shared contract fields SHALL NOT 在 acceptance 之后被 ad hoc 修改。

#### Scenario: 某组需要新的 required field

- **WHEN** 某组需要新增、删除或重命名 MVP0 contract required field
- **THEN** 它打开一个 OpenSpec change 描述 contract delta
- **AND** Runtime、Policy、Knowledge、Evaluation 相关负责人在 implementation 依赖新字段前完成评审
