# Design: Populate Static Knowledge Base

## Scope

This change is content-only. It fills the existing v1 knowledge directories:

```text
mcp_server/data/knowledge/v1/
  cards/<CARD_ID>.json
  events/<EVENT_ID>.json
  monsters/<ENEMY_ID>.json
```

It does not change runtime retrieval APIs, prompt assembly, Mod/API contracts,
or policy behavior.

## Source Handling

Entries may be generated from previously crawled HuijiWiki data, but committed
knowledge files must not reference local crawl paths. Each entry should include
repository-stable external source metadata, for example:

```json
{
  "ref": "huijiwiki:card:BASH",
  "title_zh": "灰机 wiki：痛击",
  "url": "https://sts2.huijiwiki.com/wiki/痛击",
  "retrieved_at": "2026-07-14"
}
```

If source details are incomplete, the entry should still prefer a stable web
reference over local-only references.

## Normalization Rules

- Filenames must exactly match the runtime ID:
  - `card_id` for cards;
  - `event_id` for events;
  - `enemy_id` for monsters.
- JSON must be pretty-printed with normal two-space indentation.
- Chinese prose should avoid duplicated punctuation such as `。。`.
- Static entries should describe observable facts, mechanics, move text, and
  patterns. They must not prescribe policy decisions.
- Curated existing entries should be preserved unless the change is a direct
  correction of a factual error.

## Verification

Run:

```text
cd mcp_server
uv run sts2-validate-knowledge
```

Additional local checks should confirm:

- all JSON files parse;
- filename and internal ID match;
- no placeholder source values remain;
- no local path references such as `file:///`, `local-crawl`, or `C:\Users`;
- all generated entries conform to their v1 schema.
