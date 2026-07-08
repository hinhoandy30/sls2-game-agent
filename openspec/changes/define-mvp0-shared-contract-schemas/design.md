# Design: MVP0 共享契约 Schema

## 契约优先级

MVP0 最先冻结三类接口：

1. `GameStateSnapshot`：agent 看到什么。
2. `AgentAction` / `PolicyDecision`：agent 怎么表达要做什么。
3. `StepRecord` / `RunSummary`：Evaluation 怎么读取一局游戏。

策略强度、知识丰富度、高级规划能力都可以后续逐步增强。早期真正不能乱的是这些共享契约，因为它们决定各组能否并行开发。

## Runtime 边界

只有 Runtime 可以调用真实 STS2 HTTP 或 MCP 工具。MVP0 优先使用 guided MCP 或等价 HTTP surface：

```python
class GameClient:
    def health(self) -> HealthInfo: ...
    def get_state(self) -> RawGameState: ...
    def act(self, action: AgentAction) -> ActionResult: ...
    def wait_until_actionable(self, timeout_seconds: float) -> RawGameState: ...
```

第一版 live implementation 可以在这个 adapter 背后调用 MCP guided tools，也可以直接调用 HTTP。Policy、Knowledge、Evaluation 都不能直接调用 live game API。

## GameStateSnapshot 结构

```json
{
  "schema_version": "mvp0.v1",
  "source": "mcp-guided",
  "observed_at": "2026-07-08T12:00:00Z",
  "run_id": "run_001",
  "game_version": "v0.107.1",
  "mod_version": "unknown",
  "screen": "COMBAT",
  "available_actions": ["play_card", "end_turn"],
  "state": {
    "combat": {
      "turn": 1,
      "energy": 3,
      "player": {
        "hp": 70,
        "block": 0
      },
      "hand": [
        {
          "index": 0,
          "id": "strike",
          "name": "Strike",
          "cost": 1,
          "playable": true,
          "requires_target": true,
          "valid_targets": [0]
        }
      ],
      "enemies": [
        {
          "index": 0,
          "id": "SLUDGE_SPINNER",
          "name": "Sludge Spinner",
          "hp": 35,
          "block": 0,
          "intent": {
            "type": "attack",
            "damage": 6
          }
        }
      ]
    }
  }
}
```

Runtime 可以在内部保留额外 raw data，但 Policy 只能依赖这个 normalized contract。

## AgentAction 结构

```json
{
  "action": "play_card",
  "card_index": 0,
  "target_index": 0,
  "option_index": null,
  "payload": {},
  "client_context": {
    "source": "agent-runtime"
  }
}
```

规则：

- `action` 必须出现在 `GameStateSnapshot.available_actions` 中。
- `card_index` 必须来自最新的 `state.combat.hand`。
- 只有被选中的牌需要目标时，才需要 `target_index`。
- `option_index` 用于 map、reward、shop、event、rest、timeline、character-select、selection 等选项类动作。
- Runtime 必须拒绝 stale index，而不是把过期索引发给游戏。

## PolicyDecision 结构

```json
{
  "type": "action",
  "action": {
    "action": "play_card",
    "card_index": 0,
    "target_index": 0
  },
  "reason": "Playable attack targets the only enemy.",
  "confidence": 0.7,
  "used_knowledge": ["monster:SLUDGE_SPINNER", "card:strike"]
}
```

允许的 decision type：

- `action`
- `wait`
- `stop`
- `needs_human`

`action` decision 必须包含且只包含一个 `AgentAction`。非 action decision 必须包含简短原因。

## KnowledgeContext 结构

```json
{
  "schema_version": "mvp0.v1",
  "run_id": "run_001",
  "refs": ["monster:SLUDGE_SPINNER", "card:strike"],
  "monsters": [
    {
      "id": "SLUDGE_SPINNER",
      "name": "Sludge Spinner",
      "summary": "Compact behavior summary for the current fight.",
      "source": "mcp_server/data/eng/monsters.json"
    }
  ],
  "cards": [
    {
      "id": "strike",
      "name": "Strike",
      "summary": "Compact card summary.",
      "source": "mcp_server/data/eng/cards.json"
    }
  ]
}
```

Knowledge retrieval 应该根据最新 snapshot 里的 ID 查询。MVP0 优先使用 `mcp_server/data/eng/*.json` 里的机器可读数据，markdown docs 只作为二级参考或人工整理摘要。

## StepRecord 结构

```json
{
  "schema_version": "mvp0.v1",
  "run_id": "run_001",
  "step_index": 12,
  "observed_at": "2026-07-08T12:00:01Z",
  "screen_before": "COMBAT",
  "state_summary": {
    "floor": 1,
    "player_hp": 70,
    "enemy_ids": ["SLUDGE_SPINNER"],
    "available_actions": ["play_card", "end_turn"]
  },
  "knowledge_refs": ["monster:SLUDGE_SPINNER"],
  "decision": {
    "type": "action",
    "reason": "Playable attack."
  },
  "action_request": {
    "action": "play_card",
    "card_index": 0,
    "target_index": 0
  },
  "action_result": {
    "ok": true,
    "screen_after": "COMBAT"
  },
  "error": null
}
```

Evaluation 读取 append-only JSONL records 和 summary，不应该依赖正在运行的游戏。

## Fixture 计划

MVP0 fixtures 至少覆盖：

- `MAIN_MENU`
- `CHARACTER_SELECT`
- `MAP`
- `COMBAT`
- `REWARD`

fixture 提交前必须脱敏，不能包含本地路径、Steam ID 或个人账号信息。
