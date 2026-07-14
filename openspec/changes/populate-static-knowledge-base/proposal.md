# Proposal: Populate Static Knowledge Base

## Why

The knowledge provider and JSON schemas are in place, but the curated static
knowledge base is still sparse. The agent needs broad card, event, and monster
facts to retrieve relevant Chinese context by stable game IDs during play.

Without this content, policies can only rely on live state plus a few samples,
which limits combat reasoning, event handling, reward evaluation, and debugging.

## What Changes

**Card knowledge**
- From: only schema/template coverage and a small number of examples.
- To: populate `mcp_server/data/knowledge/v1/cards/` with one JSON entry per
  known card ID, including Chinese names, type, rarity, cost, mechanics,
  upgrade summary, tags, and source references.
- Reason: reward and combat contexts need compact card facts without loading
  external pages or raw crawl data.

**Event knowledge**
- From: event lookup can load entries, but event content is mostly absent.
- To: populate `mcp_server/data/knowledge/v1/events/` with one JSON entry per
  known event ID, including Chinese names, description/options where available,
  tags, and source references.
- Reason: event decisions need stable facts about visible event choices and
  possible outcomes.

**Monster knowledge**
- From: initial curated monster examples cover only a small early-game subset.
- To: preserve curated entries and add generated entries for the remaining known
  monster IDs under `mcp_server/data/knowledge/v1/monsters/`, including Chinese
  names, move descriptions, behavior patterns, tags, and source references.
- Reason: combat policy needs monster facts and behavior hints by enemy ID.

**Contributor constraints**
- Keep runtime IDs and schema fields in English.
- Keep human-facing knowledge text in Chinese.
- Record verifiable static facts only in `cards/`, `events/`, and `monsters/`.
- Do not add policy recommendations to static fact entries.
- Do not commit local crawl files or `file:///` source references.

## Impact

- KnowledgeProvider can return broad static facts for current cards, events, and
  monsters.
- Policy prompts receive more complete retrieved context without changing the
  provider contract.
- Evaluation/debugging can trace each fact entry to a source reference.
- Strategy knowledge remains out of scope for this change.
