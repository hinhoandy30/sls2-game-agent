# Tasks: Add Agent Runtime Loop

## 1. Runtime Interfaces

- [ ] Define `GameStateSnapshot`, `AgentAction`, `PolicyDecision`, and
      `ActionResult` types in the dedicated runner package.
- [ ] Implement `GameClient.health`.
- [ ] Implement `GameClient.get_state`.
- [ ] Implement `GameClient.act`.
- [ ] Implement `GameClient.wait_until_actionable`.

## 2. Loop and Routing

- [ ] Implement the main run loop.
- [ ] Implement screen-to-policy routing.
- [ ] Add stop handling for unsupported screens.
- [ ] Add timeout handling for non-actionable states.

## 3. Validation

- [ ] Validate `action` against latest `available_actions`.
- [ ] Validate `card_index`, `option_index`, and `target_index` usage.
- [ ] Emit structured validation errors.

## 4. Verification

- [ ] Add fixture-driven Runtime tests.
- [ ] Run `openspec validate --all`.
- [ ] Smoke test against a running STS2 Mod when available.

