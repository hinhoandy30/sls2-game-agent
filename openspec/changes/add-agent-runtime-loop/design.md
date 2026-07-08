# Design: Agent Runtime Loop

## Scope

MVP0 Runtime should support the smallest useful loop:

```text
health
  -> get_state
  -> normalize GameStateSnapshot
  -> KnowledgeProvider.for_state
  -> select Policy by screen
  -> Policy.decide
  -> validate AgentAction
  -> act
  -> wait_until_actionable when needed
  -> emit StepRecord
```

## API Surface

Runtime should expose:

```python
class GameClient:
    def health(self) -> dict: ...
    def get_state(self) -> GameStateSnapshot: ...
    def act(self, action: AgentAction) -> ActionResult: ...
    def wait_until_actionable(self, timeout_seconds: float) -> GameStateSnapshot: ...
```

The first implementation may call either guided MCP tools or the equivalent HTTP
API, but Policy and Evaluation must not know which transport is used.

## Screen Routing

Runtime should route by `state.screen` and `state.session`:

- `MAIN_MENU`
- `CHARACTER_SELECT`
- `MAP`
- `COMBAT`
- `REWARD`
- `EVENT`
- `SHOP`
- `REST`
- `CHEST`
- `CARD_SELECTION`
- `MODAL`
- `GAME_OVER`

Unsupported screens should return a `needs_human` or `stop` decision with a
clear reason.

## Validation

Before executing any action, Runtime must check:

- `action` exists in `available_actions`.
- `card_index` is used only for `play_card`.
- `option_index` is present for option actions.
- `target_index` is present only when the latest state requires it.
- indexes refer to latest state, not prior state.

