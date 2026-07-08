# Design: Agent Runtime Loop

## 范围

MVP0 Runtime 的目标不是做强策略，而是提供可运行、可测试、可恢复、可记录的 agent 骨架：

```text
启动 / 连接游戏
  -> health
  -> get_state
  -> normalize GameStateSnapshot
  -> KnowledgeProvider.for_state
  -> ScreenRouter.select_policy
  -> Policy.decide
  -> Runtime.validate_action
  -> GameClient.act
  -> 等待动作完成后的 fresh actionable state
  -> append StepRecord
  -> repeat
```

## 实机采样结论

本 change 写入以下实机观察：

- 正式采样应通过 Steam 启动游戏，例如 `steam://run/2868840`；直接打开 `.app` 会出现 `No appID found`。
- `MAIN_MENU` 可用动作示例：`continue_run`、`abandon_run`、`open_timeline`。
- `REWARD` 可用动作示例：`resolve_rewards`、`collect_rewards_and_proceed`、`claim_reward`。
- `MAP` 可用动作示例：`choose_map_node`、`use_potion`、`discard_potion`。
- `COMBAT` 可用动作示例：`play_card`、`end_turn`、`use_potion`、`discard_potion`。
- `play_card` 后 action response 里的 immediate state 可能暂时只有 `save_and_quit`、`use_potion`、`discard_potion`，fresh `/state` 后才恢复 `play_card` / `end_turn`。
- `end_turn` 后 action response 可能仍显示旧 turn、旧 hand 或旧 HP，必须等待下一次 actionable state。
- 出牌后 hand index 会刷新，连续出牌必须每次根据 fresh state 重新计算 index。
- `actions/available` 对 `play_card` 的 target 描述不够细，Runtime/Policy 必须以 `combat.hand[].requires_target`、`target_index_space`、`valid_target_indices` 为准。

## GameClient

Runtime 只通过 `GameClient` 接触 live game：

```python
class GameClient:
    def health(self) -> HealthInfo: ...
    def get_state(self) -> RawGameState: ...
    def get_available_actions(self) -> AvailableActions: ...
    def act(self, action: AgentAction) -> ActionResult: ...
    def wait_until_actionable(self, timeout_seconds: float) -> RawGameState: ...
```

第一版可以实现：

- `HttpGameClient`：直接调用 `/health`、`/state`、`/actions/available`、`/action`。
- `McpGuidedGameClient`：调用 guided MCP tools。

Policy、Knowledge、Evaluation 不知道底层使用 HTTP 还是 MCP。

## Actionable State Gate

Runtime 不能把 “action response returned” 当作 “下一次可决策”。每次 `act` 后都进入 gate：

```text
act result
  -> inspect returned state
  -> if state has current-screen actionable actions, accept
  -> else poll get_state / wait_until_actionable
  -> timeout -> StepRecord error + recover/stop
```

MVP0 中 actionable 的判断至少包括：

- 当前 `screen` 已知；
- `available_actions` 不为空；
- 对当前 screen 来说存在可交给 Policy 的动作，或存在必须处理的 overlay/modal 动作；
- 对 `COMBAT`，如果还在动画/结算中且没有 `play_card` / `end_turn`，Runtime 不应请求 CombatPolicy 决策普通出牌。

## ScreenRouter

MVP0 Runtime 按 `GameStateSnapshot.screen` 路由：

- `MAIN_MENU` -> `MenuPolicy`
- `CHARACTER_SELECT` -> `CharacterSelectPolicy`
- `MAP` -> `MapPolicy`
- `COMBAT` -> `CombatPolicy`
- `REWARD` -> `RewardPolicy`
- `CARD_SELECTION` -> `SelectionPolicy`
- `EVENT` -> `EventPolicy`
- `SHOP` -> `ShopPolicy`
- `REST` -> `RestPolicy`
- `CHEST` -> `ChestPolicy`
- `MODAL` -> `ModalPolicy`
- `GAME_OVER` -> terminal handler

Overlay/selection/modal 优先级高于底层 room。比如 `CARD_SELECTION` 出现时，Runtime 应先路由到 `SelectionPolicy`，而不是继续让 `RewardPolicy` 或 `RestPolicy` 决策。

## Action Coverage

MVP0 不要求所有动作都有聪明策略，但 Runtime schema 和 validation 必须覆盖这些动作族：

- 运行流程：`continue_run`、`open_character_select`、`select_character`、`embark`、`save_and_quit`、`return_to_main_menu`
- 地图：`choose_map_node`
- 战斗：`play_card`、`end_turn`
- 药水：`use_potion`、`discard_potion`
- 奖励：`claim_reward`、`choose_reward_card`、`skip_reward_cards`、`collect_rewards_and_proceed`、`resolve_rewards`
- 选择：`select_deck_card`、`confirm_selection`
- 宝箱：`open_chest`、`choose_treasure_relic`、`proceed`
- 事件：`choose_event_option`、`proceed`
- 商店：`open_shop_inventory`、`close_shop_inventory`、`buy_card`、`buy_relic`、`buy_potion`、`remove_card_at_shop`、`proceed`
- 休息点：`choose_rest_option`，必要时进入 `CARD_SELECTION`
- 弹窗：`confirm_modal`、`dismiss_modal`

如果某个 screen/action 的 Policy 还没实现，Runtime 返回 `needs_human` 或安全停止，而不是猜一个动作。

## Validation

Runtime 在执行任何动作前验证：

- `action` 必须存在于最新 `available_actions`。
- `card_index` 只能用于 `play_card`，并且必须存在于最新 `combat.hand`。
- `target_index` 必须匹配被选中卡牌或药水的 `requires_target`、`target_index_space`、`valid_target_indices`。
- `option_index` 必须来自对应 payload 的最新 option list，例如 `map.available_nodes`、`reward.rewards`、`event.options`、`shop.*`。
- `potion_index` 必须来自最新 `run.potions`，且对应 potion `occupied=true`，并满足 `can_use` 或 `can_discard`。
- 如果 action response 和 fresh state 冲突，Runtime 以 fresh state 作为下一步决策依据。

## Retry And Failure Handling

Runtime 需要有限重试，但不能把所有错误都重试：

- `health`、`get_state`、`get_available_actions`、`wait_until_actionable` 可以按 timeout/backoff 重试。
- `act` 不能盲目重试，因为动作可能已经在游戏里生效。`act` timeout 后先 fresh `get_state`，再决定继续、记录 recoverable error 或停止。
- validation error 不重试，直接写入 `StepRecord`。
- 连续 transient failure 超过阈值后，Runtime 写 `RunSummary` 并停止。
- live bridge 断开时，Runtime 记录最后一个 state summary 和错误类型。

## 日志与诊断边界

MVP0 不让 gameplay Policy 自己读取日志、调试 Mod 或修复系统。Runtime 负责记录：

- `error_code`
- exception summary
- last screen
- last available actions
- last action request
- last state summary
- recoverability

Evaluation 或开发者事后分析这些日志。未来可以做单独的 DevDiagnostics 工具，但不属于玩游戏的 Policy。

## Future Multi-Agent

MVP0 先用单进程 Policy 插槽：

```python
class Policy:
    def decide(self, state: GameStateSnapshot, knowledge: KnowledgeContext) -> PolicyDecision: ...
```

未来 multi-agent 只替换具体 Policy 实现，比如 `CombatPolicy` 变成独立 combat agent。Runtime 仍然拥有：

- live game I/O；
- action validation；
- retry/wait；
- StepRecord；
- RunSummary。

multi-agent handoff payload 仍使用 `GameStateSnapshot`、`KnowledgeContext`、`PolicyDecision`，避免出现第二套私有协议。
