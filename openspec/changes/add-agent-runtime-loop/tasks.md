# Tasks: Add Agent Runtime Loop

## 1. Runtime Interfaces

- [x] 定义 `GameClient` interface。
- [x] 实现 `GameClient.health`。
- [x] 实现 `GameClient.get_state`。
- [x] 实现 `GameClient.get_available_actions`。
- [x] 实现 `GameClient.act`。
- [x] 实现 `GameClient.wait_until_actionable`。
- [x] 决定 MVP0 默认 adapter 是 `HttpGameClient`、`McpGuidedGameClient`，还是两者都保留。

## 2. Contracts And Models

- [x] 接入 `GameStateSnapshot` typed model 或 JSON Schema。
- [x] 接入 `AgentAction` typed model 或 JSON Schema。
- [x] 接入 `PolicyDecision` typed model 或 JSON Schema。
- [x] 接入 `ActionResult` typed model 或 JSON Schema。
- [x] 接入 `StepRecord` / `RunSummary` 输出模型。

## 3. Loop And Routing

- [x] 实现主 run loop。
- [x] 实现 action 后的 fresh actionable state gate。
- [x] 实现 screen-to-policy routing。
- [x] 实现 overlay/modal/card-selection 优先级。
- [x] 为 unsupported screen 添加 `needs_human` 或 safe stop。
- [x] 为 terminal screen 写 `RunSummary`。

## 4. MVP0 Policy Slots

- [x] 添加 `MenuPolicy` slot。
- [x] 添加 `CharacterSelectPolicy` slot。
- [x] 添加 `MapPolicy` slot。
- [x] 添加 `CombatPolicy` slot。
- [x] 添加 `RewardPolicy` slot。
- [x] 添加 `SelectionPolicy` slot。
- [x] 添加 `EventPolicy` slot。
- [x] 添加 `ShopPolicy` slot。
- [x] 添加 `RestPolicy` slot。
- [x] 添加 `ChestPolicy` slot。
- [x] 添加 `ModalPolicy` slot。

## 5. Validation

- [x] Validate `action` against latest `available_actions`。
- [x] Validate `card_index` against latest `combat.hand`。
- [x] Validate `target_index` against selected card/potion target fields。
- [ ] Validate `option_index` against latest screen payload。
- [x] Validate `potion_index` against latest `run.potions`。
- [x] Emit structured validation errors into `StepRecord`。

## 6. Retry And Failure Handling

- [ ] Add bounded retry/backoff for `health`。
- [ ] Add bounded retry/backoff for `get_state`。
- [x] Add bounded wait/timeout for `wait_until_actionable`。
- [ ] Add `act` timeout handling that fresh-reads state before deciding whether to continue。
- [x] Add consecutive failure threshold and safe run stop。
- [x] Add live bridge unavailable handling。

## 7. Verification

- [x] Add fixture-driven Runtime tests for action validation。
- [x] Add fixture test proving stale `card_index` is rejected。
- [x] Add fixture test proving `play_card` target validation uses latest hand payload。
- [x] Add fixture test proving `use_potion` can be valid outside combat when live state exposes it。
- [ ] Add fixture test for `end_turn` waiting until next actionable turn。
- [x] Add smoke test against a Steam-launched STS2 Mod when available。
- [x] Run `openspec validate --all`。
