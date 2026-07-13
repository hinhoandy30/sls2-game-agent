# Tasks: Enable Stable Combat Planning

## 1. Runtime And Prompt

- [x] 检测 current combat state 是否满足 stable plan gate。
- [x] 默认让 LLM combat policy 使用 stable action plan。
- [x] 将 action-plan response schema 收紧为 `legal_action_id` 条目。
- [x] 在 prompt 中解释 instance ID 与旧 relative index 的区别和禁止规则。
- [x] 保留 single-action fallback 与 CLI 排障开关。
- [x] 将 plan mode / fallback 原因写入 policy metadata 和 trajectory。

## 2. Verification

- [x] 添加 unit test：有 instance ID 的 combat 使用 plan prompt，且 schema 不含 raw index 字段。
- [x] 添加 unit test：缺少 instance ID 时退回 single-action prompt。
- [x] 添加 unit test：stable plan 的后续 action 在 fresh state 重新定位后执行。
- [x] Run Python unit tests。（57 tests。）
- [x] 以 Steam STS2 对 LLM plan 做一次实机 smoke test。（第 1 回合 4 项、第 2 回合 3 项，均完整执行且无 plan validation error。）
- [x] Run `openspec validate --all`。（2026-07-13：9 passed, 0 failed。）
