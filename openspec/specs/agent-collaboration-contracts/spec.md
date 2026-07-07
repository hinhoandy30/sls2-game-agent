# Agent Collaboration Contracts

## Purpose

Define the shared interfaces that allow Agent Runtime, Combat/Planner Policy,
Knowledge, and Evaluation teams to work independently while targeting one
dedicated STS2 agent runner.

## Module Boundaries

### Requirement: Runtime Owns Game I/O

The Agent Runtime SHALL be the only module that calls the STS2 HTTP/MCP action
surface.

#### Scenario: Policy wants to play a card

- GIVEN Policy receives a `GameStateSnapshot` and `KnowledgeContext`
- WHEN Policy decides to play a card
- THEN Policy returns an `AgentAction`
- AND Runtime validates that `AgentAction.action` is in `available_actions`
- AND Runtime executes the action through `act` or `/action`
- AND Policy does not call the game API directly

### Requirement: Policy Is Pure Decision Logic

Policy modules SHALL implement deterministic or LLM-backed decision functions
that accept state and knowledge and return an action or stop reason.

Required interface:

```python
class Policy:
    def decide(
        self,
        state: "GameStateSnapshot",
        knowledge: "KnowledgeContext",
        memory: "RunMemory",
    ) -> "PolicyDecision":
        ...
```

### Requirement: Knowledge Is Retrieved By ID

Knowledge modules SHALL retrieve compact relevant context using IDs present in
the live state. Knowledge SHALL NOT load full documentation files into an LLM
prompt by default.

#### Scenario: Combat starts against a known monster

- GIVEN `state.screen == "COMBAT"`
- AND `state.combat.enemies[].enemy_id` contains `SLUDGE_SPINNER`
- WHEN Runtime builds decision context
- THEN Knowledge returns a compact monster entry for `SLUDGE_SPINNER`
- AND the returned entry contains source references
- AND Runtime passes only the compact entry to Policy

### Requirement: Evaluation Consumes Logs Only

Evaluation SHALL depend on `StepRecord` and `RunSummary`, not on live game APIs.
It MAY use fixture trajectories before Runtime is complete.

## Shared Schemas

### GameStateSnapshot

`GameStateSnapshot` is the normalized state object handed from Runtime to Policy.
For the first implementation it may wrap the guided MCP `get_game_state` payload
without loss.

Required fields:

```json
{
  "schema_version": "agent-state.v1",
  "source": "mcp.get_game_state",
  "observed_at": "2026-07-07T00:00:00Z",
  "run_id": "string",
  "screen": "COMBAT",
  "session": {
    "mode": "singleplayer",
    "phase": "run",
    "control_scope": "local_player"
  },
  "turn": 1,
  "available_actions": ["play_card", "end_turn"],
  "state": {}
}
```

Rules:

- `state` SHALL contain the compact guided payload for the current screen.
- Runtime SHALL refresh this object before every decision.
- Runtime SHALL not reuse card, reward, shop, map, event, or selection indexes
  across decisions.

### AgentAction

`AgentAction` is the only object Policy returns for game control.

```json
{
  "schema_version": "agent-action.v1",
  "action": "play_card",
  "card_index": 0,
  "target_index": 0,
  "option_index": null,
  "reason": "Strike is legal and advances lethal setup.",
  "policy_id": "combat-v0",
  "confidence": 0.72
}
```

Rules:

- `action` SHALL match a current `available_actions` entry.
- `card_index` SHALL be used only for `play_card`.
- `option_index` SHALL be used for map, reward, shop, event, rest, selection,
  timeline, and character-select actions.
- `target_index` SHALL be used only when the latest state marks the card,
  potion, or rest option as requiring a target.
- Runtime SHALL reject or re-plan invalid actions before sending them to the
  game.

### PolicyDecision

```json
{
  "schema_version": "policy-decision.v1",
  "type": "action",
  "action": {},
  "alternatives": [],
  "notes": ["short rationale"],
  "requires_human": false
}
```

`type` values:

- `action`: execute the contained `AgentAction`.
- `wait`: call `wait_until_actionable`.
- `stop`: stop the run loop with a reason.
- `needs_human`: stop and request operator input.

### KnowledgeContext

```json
{
  "schema_version": "knowledge-context.v1",
  "state_ref": {
    "run_id": "string",
    "screen": "COMBAT",
    "turn": 1
  },
  "cards": {},
  "monsters": {},
  "relics": {},
  "potions": {},
  "events": {},
  "runtime_notes": [],
  "sources": []
}
```

Rules:

- Knowledge entries SHALL be keyed by stable IDs from live state.
- Entries SHOULD be compact summaries, not full markdown dumps.
- Each entry SHOULD include source metadata such as file path, data collection,
  or runtime note path.
- Knowledge MAY cache static lookups per run.

### StepRecord

`StepRecord` is the JSONL unit consumed by Evaluation.

```json
{
  "schema_version": "step-record.v1",
  "run_id": "string",
  "step_id": 12,
  "timestamp": "2026-07-07T00:00:00Z",
  "repo_commit": "string",
  "game_version": "v0.107.1",
  "screen": "COMBAT",
  "floor": 1,
  "state_summary": {},
  "knowledge_refs": [],
  "decision": {},
  "action_request": {},
  "action_result": {
    "ok": true,
    "status": "completed",
    "stable": true,
    "next_screen": "COMBAT"
  },
  "metrics_delta": {},
  "error": null
}
```

Rules:

- Runtime SHALL append one `StepRecord` for every attempted action.
- Runtime SHOULD also append records for stop conditions and unrecoverable
  invalid states.
- Evaluation SHALL treat this file as append-only input.

### RunSummary

```json
{
  "schema_version": "run-summary.v1",
  "run_id": "string",
  "seed": "string",
  "character": "IRONCLAD",
  "ascension": 0,
  "started_at": "2026-07-07T00:00:00Z",
  "ended_at": "2026-07-07T00:30:00Z",
  "result": "in_progress",
  "floor_reached": 1,
  "act_reached": "ACT_1",
  "invalid_action_count": 0,
  "recoverable_error_count": 0,
  "token_estimate": null,
  "notes": []
}
```

## Collaboration Order

Teams MAY work in parallel after this spec is accepted.

- Runtime team implements `GameClient`, `ScreenRouter`, and `RunLoop` against
  the schemas above.
- Policy team implements `Policy.decide` against fixtures without a live game.
- Knowledge team implements `KnowledgeProvider.for_state` using game data and
  docs indexes.
- Evaluation team implements `StepRecord` readers, metrics, and reports using
  mock trajectories.
- Mod/API team fixes missing game controls and state-contract bugs discovered
  by Runtime or Evaluation.

## Minimum Fixture Set

The repository SHOULD include fixtures for:

- `MAIN_MENU` with `open_character_select`.
- `CHARACTER_SELECT` with at least one unlocked character.
- `MAP` with two node options.
- `COMBAT` against one enemy with attack and block choices.
- `REWARD` with a card reward and proceed option.
- `EVENT`, `SHOP`, `REST`, and `CHEST` once those screens enter scope.

