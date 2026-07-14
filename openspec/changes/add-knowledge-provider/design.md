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
2. `mcp_server/data/knowledge/v1/<kind>/<ID>.json` for compact, curated Chinese facts;
3. `mcp_server/data/eng/*.json` for exported static game data;
4. `docs/game-knowledge/*.md` for legacy/generated behavior notes;
5. `agent_knowledge/` for runtime observations awaiting curation.

## Retrieval Rules

- Extract IDs from the current state.
- Load compact JSON entries only for those IDs.
- Cache static entries during a run.
- Validate every loaded entry with Pydantic and return external source references plus a repository-relative `knowledge_path`.
- Do not return full docs unless debug mode requests it.

## Initial File Layout

```text
mcp_server/data/knowledge/v1/
  monsters/<ENEMY_ID>.json
  events/<EVENT_ID>.json
```

Knowledge prose is Chinese, while filenames and lookup IDs remain the exact IDs returned by the Mod.
The current turn's exact damage and event options must remain sourced from live state; static JSON describes
patterns and durable facts only.

## Prompt Assembly And Cache Boundaries

`OpenAICompatiblePolicy` uses `PromptBuilder` to emit messages in this fixed order:

1. stable system rule;
2. screen contract (instruction, response schema, plan rules);
3. canonical knowledge packet;
4. dynamic decision state (live state and current legal actions).

The model provider receives only these messages. Knowledge packet lists are sorted by stable ID and encoded as
canonical JSON, so the same lookup facts produce the same bytes even when Mod entity order varies. Dynamic live
state remains last because it changes on every turn. The runtime records `layout_version`, a 16-character
`knowledge_packet_hash`, and per-message character counts in the LLM metrics. Provider-returned `cached_tokens`
remains the only evidence of an actual remote cache hit.
