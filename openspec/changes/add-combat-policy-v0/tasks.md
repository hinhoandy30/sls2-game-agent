# Tasks: Add Combat Policy V0

## 1. Interface

- [ ] Implement `CombatPolicyV0.decide`.
- [ ] Return `PolicyDecision` only.
- [ ] Avoid direct game API calls.

## 2. Heuristics

- [ ] Detect basic lethal from current hand and enemy HP.
- [ ] Prefer legal attacks when safe.
- [ ] Prefer block when incoming damage is high.
- [ ] End turn when no useful legal action remains.

## 3. Fixtures

- [ ] Add single-enemy combat fixture.
- [ ] Add low-HP danger fixture.
- [ ] Add no-playable-card fixture.

## 4. Verification

- [ ] Add unit tests for each fixture.
- [ ] Run `openspec validate --all`.

