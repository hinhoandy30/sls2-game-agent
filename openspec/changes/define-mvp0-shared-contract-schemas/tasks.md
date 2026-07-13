# Tasks

## 契约评审

- [ ] Runtime、Policy、Knowledge、Evaluation 负责人一起评审这个 change。
- [x] 确认 MVP0 所有记录统一使用 `schema_version = "mvp0.v1"`。
- [x] 确认第一版 runner 使用 `GameClient`，而不是让 Policy 直接调用 MCP 或 HTTP。
- [x] 确认第一版 `GameClient` adapter 使用 MCP guided tools、直接 HTTP，还是两者都支持但藏在同一个接口后面。（当前选择直接 HTTP；MCP wrapper 仍可供人工调试。）

## Schema 产物

- [x] 为 `GameStateSnapshot` 添加 Python typed model 或 JSON Schema。
- [x] 为 `AgentAction` 添加 Python typed model 或 JSON Schema。
- [x] 为 `PolicyDecision` 添加 Python typed model 或 JSON Schema。
- [x] 为 `KnowledgeContext` 添加 Python typed model 或 JSON Schema。
- [x] 为 `StepRecord` 添加 Python typed model 或 JSON Schema。
- [x] 为 `RunSummary` 添加 Python typed model 或 JSON Schema。

## Fixtures

- [ ] 添加脱敏后的 `MAIN_MENU` fixture。
- [ ] 添加脱敏后的 `CHARACTER_SELECT` fixture。
- [ ] 添加脱敏后的 `MAP` fixture。
- [ ] 添加脱敏后的 `COMBAT` fixture。
- [ ] 添加脱敏后的 `REWARD` fixture。
- [ ] 添加一个 Evaluation 可以在没有 STS2 的情况下读取的 fixture trajectory JSONL。

## 验证

- [ ] 添加 fixture schema validation tests。
- [x] 添加 Runtime validation test，确认 unavailable action 会被拒绝。
- [x] 添加 Runtime validation test，确认 stale `card_index` 会被拒绝。
- [x] 添加 CombatPolicyV0 fixture test，确认能返回合法 `play_card`。
- [ ] 添加 Evaluation fixture test，确认能报告 final screen、invalid actions、recoverable errors 和 floor reached。
