# Delta for Combat Policy

## ADDED Requirements

### Requirement: Combat Agent Produces A Short Tactical Audit

CombatAgent SHALL apply a fixed tactical check before selecting a combat action plan and return a short
machine-readable audit with the decision.

#### Scenario: Combat action plan is requested

- **WHEN** the current screen is `COMBAT` and stable combat planning is enabled
- **THEN** the prompt requires a primary target, lethal assessment, defense posture, risk summary, and replan boundary list
- **AND** the resulting trajectory decision stores the validated audit

#### Scenario: Hidden pile contents are unavailable

- **WHEN** the Mod has not exposed complete draw, discard, or exhaust pile contents
- **THEN** CombatAgent MUST NOT claim that a specific next-turn draw is guaranteed
- **AND** it may treat whole-deck composition only as uncertain context

### Requirement: Runtime Enforces Declared Information Boundaries

Runtime SHALL stop a multi-action combat plan at its first declared information boundary and re-read state before
the next policy decision.

#### Scenario: Plan reaches a declared draw boundary

- **WHEN** CombatAgent returns a plan containing a draw boundary action followed by more actions
- **THEN** Runtime executes through the boundary action
- **AND** it does not execute the following planned action
- **AND** the trajectory records `tactical_replan:draw_cards`
