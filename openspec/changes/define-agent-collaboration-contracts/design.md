# Design: Agent Collaboration Contracts

## Design Goals

- Keep the first dedicated agent simple: single process, modular policies.
- Preserve a path to future planner/combat multi-agent orchestration.
- Make Evaluation independent from a live game.
- Avoid loading full docs into prompts.
- Make invalid action and stale index bugs visible in logs.

## Runtime Flow

```text
health_check
  -> get_game_state
  -> normalize GameStateSnapshot
  -> KnowledgeProvider.for_state
  -> ScreenRouter.select_policy
  -> Policy.decide
  -> Runtime.validate_action
  -> act
  -> wait_until_actionable when needed
  -> append StepRecord
  -> repeat
```

## Knowledge Flow

Knowledge retrieval is state-driven:

```text
live state IDs
  -> static game data lookup
  -> runtime notes lookup
  -> compact KnowledgeContext
  -> Policy
```

The first implementation should prefer machine-readable data from
`mcp_server/data/eng/*.json` and only use markdown docs as secondary references
or curated summaries.

## Parallel Development Strategy

Each team can start with fixtures:

- Runtime owns fixture capture from live game once possible.
- Policy owns expected action decisions for each fixture.
- Knowledge owns expected compact summaries for each fixture.
- Evaluation owns expected metric output for fixture trajectories.

## Future Multi-Agent Path

The first implementation should use normal Python classes:

```python
PlannerPolicy
CombatPolicy
RewardPolicy
EventPolicy
```

If LLM sub-agents are later introduced, the same `GameStateSnapshot`,
`KnowledgeContext`, and `PolicyDecision` contracts should be used as the handoff
payloads. This avoids coupling the project to Codex, Claude Code, or any
specific orchestrator.

## Open Questions

- Whether the first runner should call MCP tools directly or call the HTTP API
  while keeping MCP as compatibility surface.
- Whether `state.state` should store the full guided payload or a normalized
  subset for every screen.
- How much card/monster/relic metadata should be stored in `StepRecord` versus
  referenced by ID.
- Whether token usage can be measured directly by the chosen LLM provider or
  estimated from prompt/output logs.

