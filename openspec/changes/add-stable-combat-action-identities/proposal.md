# Proposal: Add Stable Combat Action Identities

## 为什么

当前 combat API 用 `card_index` 和 `target_index` 指向手牌、敌人。它们只在单次 state
snapshot 内有效：一张牌被打出、烧毁、弃置、抽取，或一个敌人死亡后，后续 index 可能任意改变。

这使 LLM 无法安全地一次规划多个动作。把 index 简单减一不正确，因为手牌变化并非总是只移除
一个较早位置的元素。

## 改什么

- C# Mod 为 live `CardModel` 与 enemy `Creature` 分配进程内稳定的 instance ID。
- `/state.combat` 和 compact `agent_view.combat` 暴露这些 ID，同时保留旧 index 字段。
- `play_card` 接受可选 `card_instance_id`、`target_instance_id`；若提供，Mod 在**当前** live
  hand/enemy 列表中解析它们。旧的 index 请求保持兼容。
- Python Runtime 将 ID 保留在 `AgentAction` 与 `legal_actions` 中；一个 legal action 的 ID
  以 stable instance ID 为核心，而不是以当前 index 为核心。
- LLM 短 action plan 的每一步仍 wait/fresh-read/validate；计划中的实体不存在、目标不可用、
  screen 改变或出现选择界面时，Runtime 停止余下步骤并重新规划。

## 不改什么

- 不向 C# Mod 发送盲目批量动作，也不在 Mod 内部自动连播整套 plan。
- 不把这些 ID 当作跨游戏重启、跨 save/continue 或跨进程的持久 ID。
- 不把现有 `state_version` 当局面 revision；它是协议版本常量。
- 不在本 change 中处理 potion、shop、reward、deck selection 的稳定实体 ID。

## 影响

- Runtime/Policy 可以减少每张普通牌都调用 LLM 的成本，同时保留每步的安全检查和可观测性。
- Mod/API 负责 live 实体到临时 index 的最终解析，避免 Python 以过期位置直接控制游戏。
- Evaluation 可通过 trajectory 中的 instance ID 复盘一条计划实际使用了哪些实体。

