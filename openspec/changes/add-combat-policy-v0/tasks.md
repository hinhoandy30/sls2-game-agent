# Tasks: Add Combat Policy V0

## 1. Interface

- [x] Implement `CombatPolicyV0.decide`。（当前是可运行的基础启发式，不是最终战斗策略。）
- [x] Return `PolicyDecision` only.
- [x] Avoid direct game API calls.

## 2. Heuristics

- [ ] Detect basic lethal from current hand and enemy HP.
- [ ] Prefer legal attacks when safe.
- [ ] Prefer block when incoming damage is high.
- [x] End turn when no useful legal action remains.

## 3. Fixtures

- [ ] Add single-enemy combat fixture.
- [ ] Add low-HP danger fixture.
- [ ] Add no-playable-card fixture.

## 4. Verification

- [ ] Add unit tests for each fixture.
- [ ] Run `openspec validate --all`。（当前开发 shell 未找到 `openspec` CLI。）
