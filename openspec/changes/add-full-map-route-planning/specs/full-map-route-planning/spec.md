# full-map-route-planning 规格

## ADDED Requirements

### Requirement: 地图状态提供稳定图结构

C# Mod SHALL expose stable map graph node identity for route planning.

#### Scenario: 地图节点拥有稳定身份和边

Given 当前状态包含 `map.nodes`
Then 每个节点 SHALL include `node_id`
And 每个节点 SHALL include `parent_node_ids`
And 每个节点 SHALL include `child_node_ids`

#### Scenario: 可选地图节点绑定稳定身份

Given 当前状态包含 `map.available_nodes`
Then 每个可选节点 SHALL include `node_id`
And Runtime SHALL be able to map that node to a `choose_map_node` legal action.

### Requirement: Runtime 枚举剩余路线

Runtime SHALL generate route candidates for MAP decisions.

#### Scenario: 从当前位置重新规划

Given 玩家已经站在地图中间节点
When Runtime 生成 `route_planning`
Then 每条 `RouteCandidate.remaining_sequence` SHALL start from a currently available next node
And `remaining_counts` SHALL only count future nodes
And visited nodes SHALL NOT be counted as future rewards or risks.

#### Scenario: MAP prompt 使用下一步路线分组

Given Runtime has generated full route candidates
When building an LLM prompt for MAP
Then `route_planning.route_groups` SHALL group routes by the currently selectable next node
And each group SHALL include count ranges for `elite`, `rest`, `shop`, `monster`, and `event`
And each group SHALL include representative routes with remaining sequence information
And the prompt SHALL NOT include the full raw `map.nodes` graph.

#### Scenario: Route Agent 选择路线

Given `route_planning.route_groups` is present
Then each group SHOULD include `next_legal_action_id`
And Route Agent SHALL select a legal action id instead of inventing coordinates or option indices.
