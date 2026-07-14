# 设计：全量地图路线规划

## C# 状态输出

`map.nodes` 保持全量图结构，新增稳定字段：

- `node_id`: 使用 `"{row}:{col}"`。
- `parent_node_ids`: 父节点 id 列表。
- `child_node_ids`: 子节点 id 列表。

`map.available_nodes` 也暴露 `node_id`，让 runtime 可以把下一步候选路线绑定到稳定 legal action。

## Runtime 路线枚举

Runtime 在 `MAP` screen 构造 `state.route_planning`：

- 从 `map.available_nodes` 开始 DFS。
- 每条路线的 `remaining_sequence` 和 `remaining_counts` 只统计未来节点。
- `visited_prefix` 只用于复盘和判断是否延续旧路线，不参与未来统计。
- 全量 `route_candidates` 可用于日志和评测。
- 给 Route Agent 的 MAP prompt 默认使用 `route_groups`：按下一步节点聚合，展示精英、火堆、商店、小怪、事件等数量范围和少量代表路线。
- 每个 route group 带 `next_legal_action_id`，Route Agent 直接选择这个 id。
- MAP prompt 的 `state.map` 不包含完整 `nodes`，完整地图只在 Runtime 内部用于 DFS。

## 取舍

当前不做代码排序和战略打分。代码只做枚举、计数、分组、代表路线采样和稳定 action 绑定；Route Agent 负责结合血量、牌组、金币和战略偏好判断下一步。
