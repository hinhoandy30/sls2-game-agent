# Tasks: Populate Static Knowledge Base

## 0. OpenSpec Review

- [x] Add proposal, design notes, and knowledge-provider spec delta.
- [x] Run `openspec validate --all`.
- [ ] Review and approve the OpenSpec PR before implementation.

## 1. Card Entries

- [ ] Generate card entries from source data.
- [ ] Fill `mcp_server/data/knowledge/v1/cards/` using the existing card template.
- [ ] Include upgrade summaries where available.
- [ ] Keep source references stable and non-local.

## 2. Event Entries

- [ ] Generate event entries from source data.
- [ ] Fill `mcp_server/data/knowledge/v1/events/` using the existing event template.
- [ ] Include event options/outcome text where available.
- [ ] Keep source references stable and non-local.

## 3. Monster Entries

- [ ] Preserve existing curated monster entries.
- [ ] Generate missing monster entries from source data.
- [ ] Fill `mcp_server/data/knowledge/v1/monsters/` using the existing monster template.
- [ ] Include move descriptions and behavior patterns where available.
- [ ] Keep source references stable and non-local.

## 4. Formatting And Cleanup

- [ ] Pretty-print generated JSON.
- [ ] Normalize duplicated punctuation in generated Chinese text.
- [ ] Confirm no local crawler scripts or raw crawl files are committed.

## 5. Verification

- [ ] Run `uv run sts2-validate-knowledge`.
- [ ] Check filename/internal ID consistency.
- [ ] Check generated JSON for placeholder and local source references.
- [ ] Run `openspec validate --all`.
