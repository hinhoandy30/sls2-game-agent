# Tasks: Add Knowledge Provider

## 1. Interface

- [x] Define `KnowledgeContext`.
- [x] Implement `KnowledgeProvider.for_state`。（按 live ID 加载当前已有的中文 monster/event JSON；card/potion/relic 仍待实现。）
- [x] Add source reference shape。（每个 source 含外部 `ref`/`url` 与仓库相对 `knowledge_path`。）

## 2. Static Data Lookup

- [x] Load card data by `card_id`。（已定义 `cards/<CARD_ID>.json` schema，并按手牌 `card_id` 动态加载。）
- [x] Load monster data by `enemy_id`。（初始覆盖 Overgrowth 前 3 场弱敌池的 7 个 enemy ID。）
- [ ] Load potion data by `potion_id`.
- [x] Add event lookup stub.
- [ ] Add relic lookup stub.
- [x] Define conditional card-priority strategy schema。（`strategy/card_priorities/<CARD_ID>.json`，仅定义与校验，暂不自动注入 prompt。）

## 3. Runtime Notes

- [x] Read combat notes by enemy key when available.
- [x] Read event notes by event id when available.
- [x] Include note paths as sources.

## 4. Verification

- [x] Add fixture tests for combat state.
- [x] Add fixture tests for reward/event state.
- [x] Add knowledge JSON validator for contributor PRs.
- [x] Run `openspec validate --all`。（2026-07-13：9 passed, 0 failed。）

## 5. Prompt Assembly And Observability

- [x] Split LLM input into stable rules, screen contract, canonical knowledge packet, and dynamic state messages.
- [x] Canonicalize knowledge ordering and record a knowledge packet hash.
- [x] Record per-message character counts with the LLM metrics; retain provider `cached_tokens` when supplied.
- [x] Add prompt ordering and deterministic-hash tests.

## 6. Team Authoring Workflow

- [x] Add GitHub issue templates for monster and event knowledge entries.
- [x] Add GitHub issue templates for card facts and card-priority strategy entries.
- [x] Add PR checklist item for `uv run sts2-validate-knowledge`.
- [x] Document knowledge PR flow in `.github/CONTRIBUTING.md`.
