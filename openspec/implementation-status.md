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
- `--llm-action-plan` 是可选实验：每项动作之后都重新读状态并验证；一旦 index/target
  失效或 screen 改变，就停止余下计划。

## 最近实现记录

| Commit | 内容 | 团队影响 |
| --- | --- | --- |
| `c7d3760` | 记录 runtime 用时与 LLM token usage | Evaluation 可以比较时延、token 与局面结果。 |
| `94b67c2` | Pydantic `ActionSpec`、instant 启动、CLI 生命周期控制 | LLM 参数错误更早失败；实机测试可加速并可清理。 |
| `42cc190` | 可选短 action plan、LLM JSON 修复/读取重试 | 可做吞吐实验，但不应作为严谨战术规划依赖。 |
| `eeda540` | `legal_actions`、trajectory segment、state hash | 减少 index 猜测；checkpoint 重打不再伪装成同一线性轨迹。 |

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
- `legal_action_id` 内部仍可能包含当前的 card/enemy index，因此只对**当前 snapshot**有效。
  不能把一个 ID 带到下一次 draw、出牌、击杀或 screen 切换后重用。
- 多步 LLM plan 在 index 变化时会安全地停止，但不会自动重规划。高质量连招需要
  tactical solver，或每一步由 Policy 用 fresh state 单独决策。
- `continue_run` 的 segment 检测只覆盖同一 Runtime 进程。不同命令、不同 output 目录
  的 run 尚未自动关联为同一存档树。
- option payload 的“索引必须属于对应 option 列表”仍未完整验证；目前 `ActionSpec` 保证
  参数名，Runtime 保证 option index 存在。该项仍保留在 Runtime change 的待办。
- `health`/`get_state` 尚未实现统一 bounded retry，`act` 超时后也尚未有“先读状态再判定
  是否已执行”的专门恢复路径。
- KnowledgeProvider 目前只提取 monster/card/potion refs，不做实际资料检索；Evaluation
  JSONL reader、指标报表和脱敏 fixture 也尚未完成。

## 验证证据

- `mcp_server/tests` 当前有 53 个 unittest，覆盖 ActionSpec、参数归一化、stale card
  index、药水 slot 合法性、legal action ID、action plan 截断、运行时间/token 汇总及
  checkpoint segment。
- 最近一次实机短测在 STS2 正式版 `v0.107.1` 上到达第 8 层并自然结束，记录
  `error_count = 0`。这证明 Runtime 链路能运行；不代表策略强度或连胜能力已验证。
- 当前 shell 未找到 `openspec` CLI，因此本次尚未重新执行 `openspec validate --all`；
  这项在各 change 的 checklist 中保持未完成，恢复 CLI 后应优先补跑。

## 接下来按组开工

- Runtime/Mod API：把 `legal_actions` 和完整 option 可用性下沉到 C# bridge；补齐 read/act
  retry 与跨进程 resume lineage。
- Policy：先以 single-action + fresh state 为基线；商店、事件、药水语义和战斗策略单独开
  OpenSpec change，不与 Runtime 修复混在一起。
- Knowledge：实现按 live ID 检索、紧凑摘要和 source refs。
- Evaluation：先提交脱敏 fixture trajectory 与 JSONL reader，再做胜率、伤害、错误和成本报表。
