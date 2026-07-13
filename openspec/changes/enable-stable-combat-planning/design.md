# Design: Stable Combat Planning

## 两层循环

```text
LLM plan once
  -> [legal_action_id, legal_action_id, ...]
  -> Runtime execute one action
  -> wait / fresh state
  -> resolve same instance IDs to current indexes
  -> validate next action
  -> repeat without another LLM call
```

只有当前 plan 完成、后续 ID 已不存在、screen 改变、action window 消失或 validation 失败时，
外层 Runtime loop 才再次调用 Policy/LLM。

## Prompt Contract

在 `COMBAT` + stable identity 可用时，response schema 只允许：

```json
{
  "type": "action",
  "action_plan": {
    "actions": [
      {"legal_action_id": "play_card_card-2_enemy-1"},
      {"legal_action_id": "end_turn"}
    ],
    "stop_conditions": ["entity_missing", "screen_changed", "new_selection"]
  },
  "reason": "...",
  "confidence": 0.7
}
```

Prompt 明确说明：`card_index` / `target_index` 是旧 snapshot 的临时坐标，绝不能在 action plan
输出或用 `-1` 算法修正。`legal_action_id` 由 Runtime 从当前 Mod state 生成，combat card action
内含稳定 instance identity。

## Feature Gate

只有以下条件同时满足才启用 plan：

- screen 是 `COMBAT`；
- 每个可出 card action 都有 `card_instance_id`；
- 需要 enemy target 的 card action 也有 `target_instance_id`。

否则 Policy 回到既有 single-action prompt。这样旧 Mod、异常 state 或尚未实现 player-instance
target 的场景不会获得错误的多步承诺。

## CLI

LLM policy 默认尝试 stable plan。`--single-action` 显式关闭它，供 A/B 比较、故障定位或旧 bridge
使用。历史 `--llm-action-plan` 仍被接受，但默认行为已经等价于启用它。

