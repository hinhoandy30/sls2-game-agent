# 任务

- [x] 为 C# 地图节点和可选节点添加稳定 `node_id`。
- [x] 为 C# 地图图节点添加 `parent_node_ids` 和 `child_node_ids`。
- [x] 在 Runtime 中实现从当前位置可走节点开始的 DFS 剩余路线枚举。
- [x] 为每条 RouteCandidate 输出未来顺序、未来统计、客观特征和下一步 legal action。
- [x] 为 MAP prompt 输出按下一步节点聚合的 `route_groups`，重点包含精英、火堆、商店和小怪数量范围。
- [x] 从 MAP prompt 的 `state.map` 移除完整 `nodes`，避免把全图重复塞给模型。
- [x] 将 `route_planning` 注入 MAP prompt。
- [x] 更新 Route Agent 外部策略文本，要求使用 `next_legal_action_id`。
- [x] 添加单元测试覆盖中途重规划时只统计未来节点。
- [x] 使用真实游戏状态确认 `map.nodes` 在 v0.107.1 中能返回全量图，而不是只返回可见节点。
