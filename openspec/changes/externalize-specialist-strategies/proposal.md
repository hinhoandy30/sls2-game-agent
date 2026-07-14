# Proposal: 将专项 Agent 策略外置为版本化配置

## Why

战斗、路线和局外发展策略此前以内联字符串存在于 Python 编排代码中。策略组修改规则必须改 Runtime
代码，难以做 A/B 实验、版本回退和轨迹复现，也容易把策略变更与执行层改动混在同一个 PR。

## What Changes

- 在 `mcp_server/data/strategies/v1/` 为 Combat、RouteStrategy 和 RunDevelopment 分别维护中文 JSON
  策略文件。
- 使用 Pydantic 校验 schema、agent 名称、版本和规则内容；缺失或非法策略阻止专项 Agent 启动。
- `AgentOrchestrator` 从策略 Provider 加载规则，只把渲染后的策略传给 LLM；Runtime 的 state 读取、
  action 校验和执行职责不改变。
- 每条专项 Agent 决策记录 `strategy_id`、`strategy_revision` 与策略内容 hash。
- CLI 支持 `--strategy-dir`，供实验运行临时指向另一套策略目录。

## Non-goals

- 不实现热更新；修改策略后应启动新的 Runtime 进程。
- 不把游戏事实、怪物数据或历史复盘混入策略文件。
- 不改变 `combat_audit`、ActionSpec 或 Mod API 合约。
