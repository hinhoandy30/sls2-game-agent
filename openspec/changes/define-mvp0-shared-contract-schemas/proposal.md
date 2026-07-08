# Change: 定义 MVP0 共享契约 Schema

## 为什么

团队要并行开发第一个专用 STS2 agent，最先需要稳定的是共享接口。
Runtime、Policy、Knowledge、Evaluation 不应该互相等待，也不应该各自从 live MCP payload 里猜字段名。

我们之前已经在 macOS + STS2 `v0.107.1` 上验证过最小游戏控制链路：

- health check 可以成功；
- 可以读取当前游戏状态；
- 可以选择 Ironclad；
- 可以进入地图节点；
- 战斗中可以打需要目标的牌，也可以结束回合；
- 第一场战斗可以打到奖励页。

这些实测结果足够支撑 MVP0 先冻结这些契约：状态快照、标准动作、策略决策、知识上下文、轨迹记录。

## 改什么

- 新增 `mvp0-shared-contracts`，作为 `agent-collaboration-contracts` 之下更具体的 MVP0 字段契约。
- 定义 Runtime 拥有的 `GameClient` 边界。
- 定义以下对象的必需字段：
  - `GameStateSnapshot`
  - `AgentAction`
  - `PolicyDecision`
  - `KnowledgeContext`
  - `StepRecord`
  - `RunSummary`
- 定义并行开发所需的最小 fixture 覆盖范围。
- 要求 MVP0 记录统一使用 `schema_version = "mvp0.v1"`。

## 影响

- Runtime 可以先实现 live game loop，不阻塞 Policy。
- Policy 可以完全基于 fixture 测试。
- Evaluation 可以先读 fixture trajectory，不需要真实 STS2 进程。
- Knowledge 可以根据最新 state 里的 ID 返回紧凑上下文。
- 后续如果要改共享字段，需要先开 OpenSpec change，而不是在代码里临时改。
