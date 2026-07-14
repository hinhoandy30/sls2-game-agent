# Proposal: 强化战斗策略检查并支持固定种子开局

## Why

当前 CombatAgent 能稳定执行合法动作，但其提示词没有固定的战术检查顺序，日志中出现了
高战损、未显式检查斩杀与防御取舍的决策。评测也需要可重复的开局；虽然 Mod 已能读取
run seed，但角色选择 API 尚不能设置 seed。

## What Changes

- 为 CombatAgent 增加固定、可复盘的战斗检查协议：目标优先级、当回合斩杀、本回合伤害
  与防御取舍、药水、以及信息边界。
- 要求战斗 LLM 返回短 `combat_audit`，记录结论而非冗长推理链；Runtime 将它写入轨迹。
- 将抽牌、随机、生成牌、弃牌、消耗、未知复杂牌和目标死亡标记为重规划边界。Runtime 在
  执行到模型声明的边界后停止当前 action plan 并从 fresh state 再决策。
- 在角色选择阶段增加 `set_seed(seed)` action。该 action 仅允许单人或主机、未出发的
  StartRunLobby 使用；标准单人模式直接更新 lobby seed，避免不支持的 UI callback，并在响应 state
  中验证 `character_select.seed` 回显。
- CLI 增加显式 `--seed` bootstrap，供评测在新开局前设置固定种子。

## Non-goals

- 不实现全卡牌、全回合、全随机性的求解器。
- 不使用存档回滚或 save scumming 来选择动作。
- 不让 CombatAgent 或 CLI 在已有 run 中修改种子。

## Impact

- Affected code: `STS2AIAgent` C# action/state bridge, Python LLM prompt/runtime/CLI/tests.
- Affected capability: combat policy and reproducible seeded runs.
