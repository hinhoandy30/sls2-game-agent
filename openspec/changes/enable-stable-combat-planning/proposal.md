# Proposal: Enable Stable Combat Planning

## 为什么

稳定 card/enemy instance ID 已经在 Mod、Runtime 和实机 smoke test 中验证。继续每打出一张牌
都调用一次 LLM 会产生不必要的 token、时延和上下文重复，也不能让模型先整体考虑当前手牌的能量
分配、目标和结束回合。

## 改什么

- LLM Runtime 在具有 stable combat identity 的战斗中默认进入 action-plan mode。
- Prompt 要求模型一次返回最多 `max_plan_actions` 个 `legal_action_id`，禁止在 plan 中输出
  `card_index`、`target_index` 或相对位置推理。
- Runtime 在每个动作后 fresh-read 并按 instance ID 重新定位当前 card/target；它不再次调用 LLM，
  直到完成计划或触发安全停止条件。
- 缺少 stable ID 的旧 bridge、包含当前不支持稳定 enemy target 的 action，自动退回单动作。
- CLI 提供 `--single-action` 排障开关；旧 `--llm-action-plan` 保持可识别兼容。

## 不改什么

- 不在 Mod 内批量排队整套动作。
- 不保证计划跨抽牌、生成牌、烧牌、弃牌、敌人死亡、选择界面或 screen 切换仍可继续。
- 不把 policy 策略质量（例如商店、事件风险）混入本 change。

