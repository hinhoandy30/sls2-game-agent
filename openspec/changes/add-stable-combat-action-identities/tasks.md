# Tasks: Add Stable Combat Action Identities

## 1. Contract

- [x] 定义 card/enemy 的进程内 stable instance ID 边界。
- [x] 明确 `state_version` 不是局面 revision，不将其用于 action concurrency。
- [x] 定义 `play_card` 的 instance-ID-first、index-backward-compatible 请求规则。

## 2. Mod/API

- [x] 为 live `CardModel` 分配并输出 `card_instance_id`。
- [x] 为 live enemy `Creature` 分配并输出 `enemy_instance_id`。
- [x] 在 raw combat state 与 compact agent view 输出上述 ID。
- [x] 让 `play_card` 解析 `card_instance_id`，并对 stale ID 返回 structured error。
- [x] 让 enemy-targeted `play_card` 解析 `target_instance_id`，并对 stale ID 返回 structured error。
- [x] 保持仅有 `card_index` / `target_index` 的旧客户端可用。

## 3. Python Runtime

- [x] 扩展 `AgentAction` 和 HTTP request 为 instance ID 字段。
- [x] 将 `legal_actions` 的 card/enemy action ID 建立在 stable instance ID 上。
- [x] 从 `legal_action_id` 解析 instance ID，并在 fresh state 重新验证。
- [x] LLM action-plan prompt 优先要求计划项使用 `legal_action_id`。
- [x] 在 runtime validation 中拒绝 stale card/enemy instance ID。

## 4. Verification

- [x] 添加 Python unit tests：相同 card ID 的两张牌仍以不同 instance ID 区分。
- [x] 添加 Python unit tests：后续计划的 index 失效时，instance ID 仍能在 fresh state 解析。
- [x] 添加实机 smoke test：同名 `card_1`/`card_2` 可区分；`card_1` 出牌后 `card_2` 从 index 1 移到 0，仍可仅按 ID 出牌；stale `card_1` 返回 HTTP 409。
- [ ] 添加 Mod/API tests 或可重复实机采样：弃牌/烧牌、抽牌、敌人死亡后验证 ID 生命周期。
- [x] 构建 C# Mod。（2026-07-13：项目级 .NET 9 SDK，0 warning / 0 error。）
- [x] 对 Steam 启动的 STS2 做一次 instance-ID smoke test。（STS2 v0.107.1，Mod 0.8.0，2026-07-13。）
- [ ] Run `openspec validate --all`。
