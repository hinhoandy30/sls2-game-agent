# Tasks: Add Knowledge Provider

## 1. Interface

- [x] Define `KnowledgeContext`.
- [x] Implement `KnowledgeProvider.for_state`。（按 live ID 加载当前已有的中文 monster/event JSON；card/potion/relic 仍待实现。）
- [x] Add source reference shape。（每个 source 含外部 `ref`/`url` 与仓库相对 `knowledge_path`。）

## 2. Static Data Lookup

- [ ] Load card data by `card_id`.
- [x] Load monster data by `enemy_id`。（初始覆盖 Overgrowth 前 3 场弱敌池的 7 个 enemy ID。）
- [ ] Load potion data by `potion_id`.
- [x] Add event lookup stub.
- [ ] Add relic lookup stub.

## 3. Runtime Notes

- [x] Read combat notes by enemy key when available.
- [x] Read event notes by event id when available.
- [x] Include note paths as sources.

## 4. Verification

- [x] Add fixture tests for combat state.
- [x] Add fixture tests for reward/event state.
- [x] Run `openspec validate --all`。（2026-07-13：9 passed, 0 failed。）

## 5. Prompt Assembly And Observability

- [x] Split LLM input into stable rules, screen contract, canonical knowledge packet, and dynamic state messages.
- [x] Canonicalize knowledge ordering and record a knowledge packet hash.
- [x] Record per-message character counts with the LLM metrics; retain provider `cached_tokens` when supplied.
- [x] Add prompt ordering and deterministic-hash tests.
