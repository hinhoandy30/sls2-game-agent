# Proposal: Add Knowledge Provider

## Why

The agent needs card, monster, relic, potion, and event context, but loading full
markdown documents into prompts is too expensive and unstable. Knowledge should
be retrieved by stable IDs from live state.

## What Changes

**KnowledgeProvider**
- From: Humans or prompts refer to docs manually.
- To: A `KnowledgeProvider` returns compact `KnowledgeContext` objects for the
  current state.
- Reason: Policy needs relevant context without prompt bloat.
- Impact: Knowledge team can develop retrieval independently.

**Source references**
- From: Knowledge snippets have unclear provenance.
- To: Entries include source references to extracted data, docs, or runtime
  notes.
- Reason: Decisions must be auditable.
- Impact: Evaluation and debugging can trace why Policy saw a fact.

## Impact

- Policy can consume structured knowledge.
- Evaluation can record `knowledge_refs`.
- Runtime can cache static lookups per run.

