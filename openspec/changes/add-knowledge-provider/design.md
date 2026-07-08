# Design: Knowledge Provider

## Input

KnowledgeProvider receives the latest `GameStateSnapshot`.

## Output

KnowledgeProvider returns:

```json
{
  "schema_version": "knowledge-context.v1",
  "state_ref": {},
  "cards": {},
  "monsters": {},
  "relics": {},
  "potions": {},
  "events": {},
  "runtime_notes": [],
  "sources": []
}
```

## Sources

Priority:

1. live state for legality and current values;
2. `mcp_server/data/eng/*.json` for static game data;
3. `docs/game-knowledge/*.md` for curated behavior notes;
4. `agent_knowledge/` for runtime observations.

## Retrieval Rules

- Extract IDs from the current state.
- Load compact entries only for those IDs.
- Cache static entries during a run.
- Return source references.
- Do not return full docs unless debug mode requests it.

