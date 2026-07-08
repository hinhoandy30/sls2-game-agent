# Tasks: Add Knowledge Provider

## 1. Interface

- [ ] Define `KnowledgeContext`.
- [ ] Implement `KnowledgeProvider.for_state`.
- [ ] Add source reference shape.

## 2. Static Data Lookup

- [ ] Load card data by `card_id`.
- [ ] Load monster data by `enemy_id`.
- [ ] Load potion data by `potion_id`.
- [ ] Add relic and event lookup stubs.

## 3. Runtime Notes

- [ ] Read combat notes by enemy key when available.
- [ ] Read event notes by event id when available.
- [ ] Include note paths as sources.

## 4. Verification

- [ ] Add fixture tests for combat state.
- [ ] Add fixture tests for reward/event state.
- [ ] Run `openspec validate --all`.

