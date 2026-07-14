# Design: 外置专项策略

## Directory contract

默认目录是 `mcp_server/data/strategies/v1/`，每个 specialist 有且仅有一个同名文件：

```text
combat.json
route_strategy.json
run_development.json
```

文件 schema：

```json
{
  "schema_version": "sts2-specialist-strategy.v1",
  "agent_name": "combat",
  "strategy_id": "combat.baseline.v1",
  "revision": 1,
  "title_zh": "可读标题",
  "rules_zh": [{"rule_id": "stable-id", "text_zh": "规则正文"}]
}
```

`strategy_id` 标识策略族；同一策略的措辞或规则发生行为变化时至少递增 `revision`。实验性分支应使用新
`strategy_id`，避免结果混淆。

## Runtime contract

`StrategyProvider` 在创建专项 Agent 时读取并 Pydantic 校验文件、缓存本进程内不可变版本，并将
`rules_zh` 按顺序渲染到 Agent instruction。路径可由 `STS2_STRATEGY_DIR` 或 CLI `--strategy-dir`
覆盖。路径中的文件缺失、JSON 无效或 `agent_name` 与文件名不符时直接报错，不能静默退回代码里的
隐藏策略。

每次决策的 `metadata.agent.strategy` 记录：

```json
{
  "strategy_id": "combat.baseline.v1",
  "strategy_revision": 1,
  "strategy_hash": "16-char-sha256"
}
```

因此 Evaluation 可按真实策略内容区分 trajectory；同 ID/revision 但 hash 不同应视为配置治理错误。

## Ownership

- 策略组：维护 `data/strategies/`、revision、规则测试与实验说明。
- Runtime 组：维护 Provider、schema、prompt 注入、轨迹 metadata 和 CLI override。
- Knowledge 组：维护 `data/knowledge/`，不修改策略规则来填补怪物事实。
- Evaluation 组：把 strategy metadata 纳入每次实验配置和聚合维度。
