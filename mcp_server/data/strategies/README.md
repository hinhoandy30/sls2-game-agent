# 专项策略配置

这里存放**人维护、可版本化**的 Agent 策略，而不是游戏事实知识库。

- `v1/combat.json`：战斗 Agent 的优先级、风险取舍和信息边界规则。
- `v1/route_strategy.json`：地图路线决策规则。
- `v1/run_development.json`：奖励、选牌、商店、事件、休息点和宝箱决策规则。

每个文件都由 `StrategyProvider` 和 Pydantic 严格校验。修改规则时：

1. 保持 `agent_name` 与文件名一致。
2. 逻辑发生变化时更新 `strategy_id` 或递增 `revision`。
3. 只写可执行、可检验的中文规则；游戏当前数值必须以 live state 为准。
4. 运行 `cd mcp_server && uv run python -m unittest discover -s tests`。

Runtime 会把策略的 `strategy_id`、`strategy_revision` 和内容 hash 写进 trajectory。评测必须按这些字段区分实验，不能只比较模型名。

可用 `STS2_STRATEGY_DIR=/path/to/strategies/v1` 或 CLI 的 `--strategy-dir` 临时指向一套实验策略，不改默认文件。
