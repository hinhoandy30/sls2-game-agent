# Tasks: Add Card Priority Knowledge Sample

## 1. Retrieval Contract

- [x] 1.1 Add `card_priorities` to KnowledgeContext and prompt canonicalization.
- [x] 1.2 Load card facts and optional priority entries from reward-card candidates.
- [x] 1.3 Load card facts and optional priority entries from shop-card candidates.
- [x] 1.4 Keep combat-hand lookup limited to card facts.

## 2. Initial Knowledge Batch

- [x] 2.1 Research and add `ANGER.json` priority strategy.
- [x] 2.2 Research and add `BURNING_PACT.json` priority strategy.
- [x] 2.3 Research and add `BATTLE_TRANCE.json` priority strategy.
- [x] 2.4 Research and add `OFFERING.json` priority strategy.
- [x] 2.5 Research and add `CORRUPTION.json` priority strategy.
- [x] 2.6 Update knowledge maintainer documentation for choice-scoped strategy.

## 3. Verification

- [x] 3.1 Add tests for reward/shop retrieval, missing entries, and deduplication.
- [x] 3.2 Add tests for combat exclusion and deterministic prompt ordering.
- [x] 3.3 Run `sts2-validate-knowledge`.
- [x] 3.4 Run focused Runtime unit tests.
- [x] 3.5 Run full OpenSpec validation.
- [x] 3.6 Present the uncommitted diff and verification evidence for user approval.
