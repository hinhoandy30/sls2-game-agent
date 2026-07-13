# Design: Stable Combat Action Identities

## 身份模型

Mod 使用对象引用映射为当前进程内的每个 live `CardModel` 和 enemy `Creature` 分配 ID：

```text
card_1, card_2, ...
enemy_1, enemy_2, ...
```

同一对象在 hand、discard、exhaust 间移动时应保留同一 ID；新生成或复制的卡是新的对象，因此
获得新 ID。ID 仅在 Mod 进程存活期间有效。若游戏版本在移动卡时重建 `CardModel`，该假设必须
以实机测试验证；在此之前 Runtime 不得跨 restart/continue 保存计划。

## State Contract

现有字段保持不变，并增加：

```json
{
  "combat": {
    "hand": [
      {"index": 2, "card_instance_id": "card_7", "card_id": "STRIKE_IRONCLAD"}
    ],
    "enemies": [
      {"index": 0, "enemy_instance_id": "enemy_3", "enemy_id": "SLUDGE_SPINNER"}
    ]
  }
}
```

compact agent view 使用同名字段，因此 guided/MCP consumers 无须从 raw state 推断身份。

## Action Contract

`play_card` 的新请求形状：

```json
{
  "action": "play_card",
  "card_instance_id": "card_7",
  "target_instance_id": "enemy_3"
}
```

若同时提供 instance ID 和 index，Mod 以 instance ID 为准。若实体不在当前 hand/enemy 列表，
Mod 返回 structured stale-instance error，且不出牌。只提供 index 的旧客户端继续按原逻辑工作。

不添加 `expected_state_version`：当前 `state_version` 表示 API schema/protocol，不表示随动作
递增的局面 revision。Runtime 已在每步前读取 fresh actionable state；未来若需要 optimistic
concurrency，应新增独立、单调的 `state_revision`。

## Runtime Plan Execution

LLM plan 应引用 `legal_action_id`，Runtime 从 fresh state 把它解析成：

```python
AgentAction(
    action="play_card",
    card_instance_id="card_7",
    target_instance_id="enemy_3",
    card_index=2,      # 仅为兼容/诊断，不是计划身份
    target_index=0,
)
```

执行器每一动作后 wait/fresh-read，再对下一项计划调用 validation。若 ID 已消失、目标死亡、screen
改变、出现 card selection，或后续 action 不再合法，则记录 `validation_stopped:*` 并把控制权还给
Policy。它不会猜测新的 index，也不会重放上一条 action。

## Compatibility And Rollout

1. 先增加 Mod 输出与 `play_card` 的 ID 解析，保留 index input/output。
2. Runtime 增加字段、legal action ID 与 validation，旧 LLM JSON 仍可使用 index 单动作。
3. LLM plan prompt 优先要求 `legal_action_id`。
4. 用实机测试验证出牌、烧牌、弃牌/抽牌后，存活 card 的 ID 不变；失败则停止 rollout，重新确认
   CardModel 生命周期。

