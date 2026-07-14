# Tasks

## 1. Combat policy contract

- [x] 1.1 Add combat-audit schema and allowed replan-boundary values to the LLM response contract.
- [x] 1.2 Add the fixed CombatAgent strategy protocol to its prompt and include the audit in trajectory metadata.
- [x] 1.3 Enforce the first declared boundary while executing an action plan, without weakening fresh-state validation.
- [x] 1.4 Add unit tests for audit parsing, invalid boundary repair/rejection, and boundary plan truncation.
- [x] 1.5 Route the already-exposed `BUNDLE_SELECTION` screen to RunDevelopmentAgent so seeded-run smoke tests can reach combat.

## 2. Seeded run contract

- [x] 2.1 Add `set_seed` availability, request validation and standard-mode-safe execution in the C# Mod.
- [x] 2.2 Expose `set_seed` through Python action contracts and an explicit CLI `--seed` bootstrap.
- [x] 2.3 Add Python tests for seed request construction and bootstrap screen guards.

## 3. Verification and documentation

- [x] 3.1 Build the C# Mod against the local STS2 assembly.
- [x] 3.2 Run Python unit tests and OpenSpec validation.
- [x] 3.3 Start a debug game session, set a fixed seed, verify the character-select echo, and run a short CombatAgent smoke test.
- [x] 3.4 Update project memory and user-facing setup documentation with seed and combat-audit behavior.
