# Tasks: Add Agent Runtime Loop

## 1. Runtime Interfaces

- [ ] 定义 `GameClient` interface。
- [ ] 实现 `GameClient.health`。
- [ ] 实现 `GameClient.get_state`。
- [ ] 实现 `GameClient.get_available_actions`。
- [ ] 实现 `GameClient.act`。
- [ ] 实现 `GameClient.wait_until_actionable`。
- [ ] 决定 MVP0 默认 adapter 是 `HttpGameClient`、`McpGuidedGameClient`，还是两者都保留。

## 2. Contracts And Models

- [ ] 接入 `GameStateSnapshot` typed model 或 JSON Schema。
- [ ] 接入 `AgentAction` typed model 或 JSON Schema。
- [ ] 接入 `PolicyDecision` typed model 或 JSON Schema。
- [ ] 接入 `ActionResult` typed model 或 JSON Schema。
- [ ] 接入 `StepRecord` / `RunSummary` 输出模型。

## 3. Loop And Routing

- [ ] 实现主 run loop。
- [ ] 实现 action 后的 fresh actionable state gate。
- [ ] 实现 screen-to-policy routing。
- [ ] 实现 overlay/modal/card-selection 优先级。
- [ ] 为 unsupported screen 添加 `needs_human` 或 safe stop。
- [ ] 为 terminal screen 写 `RunSummary`。

## 4. MVP0 Policy Slots

- [ ] 添加 `MenuPolicy` slot。
- [ ] 添加 `CharacterSelectPolicy` slot。
- [ ] 添加 `MapPolicy` slot。
- [ ] 添加 `CombatPolicy` slot。
- [ ] 添加 `RewardPolicy` slot。
- [ ] 添加 `SelectionPolicy` slot。
- [ ] 添加 `EventPolicy` slot。
- [ ] 添加 `ShopPolicy` slot。
- [ ] 添加 `RestPolicy` slot。
- [ ] 添加 `ChestPolicy` slot。
- [ ] 添加 `ModalPolicy` slot。

## 5. Validation

- [ ] Validate `action` against latest `available_actions`。
- [ ] Validate `card_index` against latest `combat.hand`。
- [ ] Validate `target_index` against selected card/potion target fields。
- [ ] Validate `option_index` against latest screen payload。
- [ ] Validate `potion_index` against latest `run.potions`。
- [ ] Emit structured validation errors into `StepRecord`。

## 6. Retry And Failure Handling

- [ ] Add bounded retry/backoff for `health`。
- [ ] Add bounded retry/backoff for `get_state`。
- [ ] Add bounded wait/timeout for `wait_until_actionable`。
- [ ] Add `act` timeout handling that fresh-reads state before deciding whether to continue。
- [ ] Add consecutive failure threshold and safe run stop。
- [ ] Add live bridge unavailable handling。

## 7. Verification

- [ ] Add fixture-driven Runtime tests for action validation。
- [ ] Add fixture test proving stale `card_index` is rejected。
- [ ] Add fixture test proving `play_card` target validation uses latest hand payload。
- [ ] Add fixture test proving `use_potion` can be valid outside combat when live state exposes it。
- [ ] Add fixture test for `end_turn` waiting until next actionable turn。
- [ ] Add smoke test against a Steam-launched STS2 Mod when available。
- [ ] Run `openspec validate --all`。
