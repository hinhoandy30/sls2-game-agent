# Runtime 实现状态（2026-07-13）

这份文档描述仓库**现在实际可用**的能力，而不是未来设计目标。团队在开始新
工作前，应同时阅读：

1. `specs/agent-collaboration-contracts/spec.md`：长期共享边界；
2. 对应 `changes/*/` 的 proposal、design、tasks：变更理由和未完成项；
3. 本文：已落地代码、测试证据和当前限制。

## 现在已可依赖的 Runtime 能力

- `HttpGameClient` 已连接 STS2AIAgent 的 `/health`、`/state`、
  `/actions/available`、`/action` 和等待接口；MVP0 当前选择直接 HTTP，而不是
  在 Runtime 内调用 MCP。
- `AgentRuntime` 拥有主循环：health、读取 snapshot、知识引用、screen 路由、Policy
  决策、验证、执行、等待 fresh actionable state、写 trajectory 和 summary。
- 已有 Menu、角色选择、地图、战斗、奖励、选卡、事件、商店、休息点、宝箱和 modal
  的基础 Policy 插槽。它们只是可运行的 MVP0 行为，**不是高胜率策略**。
- LLM action JSON 先经过 Pydantic `ActionSpec` 形状校验；再由 Runtime 根据 live
  state 做 card、target、potion 和 action 可用性校验。
- Runtime 从 fresh snapshot 派生具体 `legal_actions`。LLM 可以返回
  `legal_action_id`，无需自己拼 `card_index`、`option_index` 或 `potion_index`。
- CLI 可用 `--enable-instant` 向工作台 Mod console 发送 `instant`；它只负责加快
  游戏，不改变 Runtime 的“每次动作后等待可行动状态”规则。
- `--llm-action-plan` 保留为兼容 flag；stable identity 可用的 combat 默认会使用短 plan。每项
  动作之后都重新读状态并验证；实体失效或 screen 改变就停止余下计划。
- CombatAgent 会同时返回结构化 `combat_audit`（目标、斩杀、防御取舍、风险摘要、重规划边界）。
  对抽牌、随机、生成牌、弃牌/消耗等边界，Runtime 要求边界动作是 plan 最后一项，执行它后从 fresh
  state 重规划，避免以旧局面继续出牌。
- `set_seed(seed)` 已由 C# Mod、Python action contract、MCP bridge 和 CLI `--seed` 暴露；只允许
  未出发的角色选择阶段。v0.107.1 标准单人模式通过 `StartRunLobby.Seed` 私有 setter 更新状态，避免
  `SetSeed()` 调用不支持的 UI callback；端到端回显已验证。
- LLM Runtime 现在默认在 combat stable identity 可用时一次规划多张 `legal_action_id`；每张
  牌后 Runtime 重新读 state 并重新定位实体。`--single-action` 可用于排障或旧 bridge。
- `--policy multi-agent` 通过确定性 `AgentOrchestrator` 将 MAP、COMBAT 与卡组发展类 screen
  分给 RouteStrategy、Combat、RunDevelopment 专项 LLM agent；它们只返回 PolicyDecision，Runtime
  仍是唯一的 live HTTP 执行者。每局写入 `context.jsonl`，GAME_OVER 后可由 RunReviewAgent 生成
  `review.json` 与带证据的策略经验，保存到 `agent_knowledge/experience/v1/` 并按 scope 注入下一局。
- combat `card_instance_id` / `enemy_instance_id` 与 instance-ID-first `play_card` 已写入
  Mod 和 Runtime。结构化 draw/discard/exhaust pile card 同样携带 `card_instance_id`，可复盘
  卡牌跨堆移动；ID 只在当前 Mod 进程内有效。
- 专项 Agent 的策略已从 Python 内联字符串迁移至 `mcp_server/data/strategies/v1/`。每份 JSON 都由
  Pydantic 校验；轨迹的 `decision.metadata.agent.strategy` 会记录 `strategy_id`、revision 与内容 hash。
  策略实验可使用 CLI `--strategy-dir` 指向另一套版本化目录。

## 最近实现记录

| Commit | 内容 | 团队影响 |
| --- | --- | --- |
| `c7d3760` | 记录 runtime 用时与 LLM token usage | Evaluation 可以比较时延、token 与局面结果。 |
| `94b67c2` | Pydantic `ActionSpec`、instant 启动、CLI 生命周期控制 | LLM 参数错误更早失败；实机测试可加速并可清理。 |
| `42cc190` | 可选短 action plan、LLM JSON 修复/读取重试 | 可做吞吐实验，但不应作为严谨战术规划依赖。 |
| `eeda540` | `legal_actions`、trajectory segment、state hash | 减少 index 猜测；checkpoint 重打不再伪装成同一线性轨迹。 |
| `add-stable-combat-action-identities` | stable combat action identities | Mod/API 与 Runtime 以实体 ID 而不是手牌位置衔接多步计划。 |
| `enable-stable-combat-planning` | 默认 LLM combat plan | Steam smoke 中连续完整执行 4 项与 3 项 instance-ID action plan。 |
| `add-combat-policy-audit-and-seeded-runs` | 战斗审计/边界与固定种子 | Steam smoke 验证生成牌、随机消耗牌都会在边界后重新读取 state；`HYPF24C3XC` seed 回显端到端验证通过。 |
| `externalize-specialist-strategies` | 外置专项策略配置 | 策略组可独立维护中文 JSON；trajectory 可区分具体策略版本和内容。 |

## 输出文件与消费者

每次 Runtime run 会新建：

```text
runs/<timestamp>_<run-id>/
  trajectory.jsonl
  segments.jsonl
  summary.json
```

`trajectory.jsonl` 每行是 `StepRecord`，包含决策前摘要、动作、结果、错误、step 用时、
segment ID 及前后 state hash。`segments.jsonl` 描述每条 checkpoint 分支。`summary.json`
包含最终 screen/floor、错误数、总时间、token usage 和 segment 数。

Evaluation 应只读取这些文件，不直接调用 STS2。Policy 不应读取这些文件来修复 Mod 或
运行时故障。

## 已知边界，暂时不要依赖

- `legal_actions` 是 Python Runtime 派生层，不是 C# Mod/API 返回的唯一真相；Mod/API
  组后续应将等价字段下沉到 bridge。
- 安装本轮 Mod 后，combat card/enemy `legal_action_id` 将以 instance ID 为核心，可跨 index
  变化重新解析；旧 Mod 或非 combat action 仍可能依赖当前 index，不能跨 snapshot 复用。
- CombatAgent 使用稳定 `legal_action_id` 制定短 plan。它会对抽牌、随机、生成牌、弃牌/消耗、
  目标死亡和未知复杂效果声明重规划边界；Runtime 强制该动作位于 plan 末尾，执行后读取 fresh
  state 并再次调用 Policy。它不是全局 tactical solver，策略质量仍取决于模型、知识库与后续评测。
- `continue_run` 的 segment 检测只覆盖同一 Runtime 进程。不同命令、不同 output 目录
  的 run 尚未自动关联为同一存档树。
- option payload 的“索引必须属于对应 option 列表”仍未完整验证；目前 `ActionSpec` 保证
  参数名，Runtime 保证 option index 存在。该项仍保留在 Runtime change 的待办。
- `health`/`get_state` 尚未实现统一 bounded retry，`act` 超时后也尚未有“先读状态再判定
  是否已执行”的专门恢复路径。
- KnowledgeProvider 已能按当前 `enemy_id` / `event_id` 从 `mcp_server/data/knowledge/v1/` 加载
  紧凑中文 JSON。`PromptBuilder` 会把稳定系统规则、screen contract、按 ID 排序的知识包和每回合
  dynamic state 分成固定顺序消息，并在 LLM metrics 中记录 knowledge hash 与消息字符数；目前仅覆盖
  Overgrowth 前 3 场弱敌池的怪物和事件文件框架，卡牌、药水、遗物与全量事件资料仍未完成。Evaluation
  JSONL reader、指标报表和脱敏 fixture 也尚未完成。

## 验证证据

- `mcp_server/tests` 当前有 78 个 unittest，覆盖 ActionSpec、参数归一化、stale card
  index、药水 slot 合法性、legal action ID、action plan 截断、稳定 card instance ID、
  运行时间/token 汇总、checkpoint segment，以及中文知识 JSON 的 monster/event 动态加载、LLM
  prompt 注入、知识包排序与 hash 稳定性，以及专项 agent 路由、共享上下文、经验检索和 GAME_OVER
  review/经验落盘。
- 本轮 C# Mod 已使用项目级 .NET 9 SDK 干净构建；Steam 实机验证确认：`card_1` 出牌后，
  同名 `card_2` 从 index 1 移到 0 但 ID 保持不变，并且可仅按 ID 继续出牌；已离开手牌的
  `card_1` 被安全拒绝为 HTTP 409 `stale_card_instance_id`。后续生命周期采样确认：`card_2`
  从手牌 -> 弃牌 -> 抽牌堆 -> 手牌始终为同一个 ID；`ASCENDERS_BANE` 从手牌进入穷尽堆仍为
  `card_4`；死亡的 `enemy_1` 会触发 HTTP 409 `stale_target_instance_id`。
- 最近一次实机短测在 STS2 正式版 `v0.107.1` 上到达第 8 层并自然结束，记录
  `error_count = 0`。这证明 Runtime 链路能运行；不代表策略强度或连胜能力已验证。
- 本轮新增测试覆盖 `combat_audit` 的 schema、边界 repair、执行截断和 live combat piles 注入；
  `set_seed` 的参数与 CLI screen guard 也有覆盖。最新 OpenSpec 全量验证结果将在本 change 收尾时更新。

## 接下来按组开工

- Runtime/Mod API：把 `legal_actions` 和完整 option 可用性下沉到 C# bridge；补齐 read/act
  retry 与跨进程 resume lineage。
- Policy：先以 single-action + fresh state 为基线；商店、事件、药水语义和战斗策略单独开
  OpenSpec change，不与 Runtime 修复混在一起。
- Knowledge：实现按 live ID 检索、紧凑摘要和 source refs。
- Evaluation：先提交脱敏 fixture trajectory 与 JSONL reader，再做胜率、伤害、错误和成本报表。
