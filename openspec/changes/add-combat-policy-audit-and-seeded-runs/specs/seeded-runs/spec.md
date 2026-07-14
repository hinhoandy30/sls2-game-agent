# Delta for Seeded Runs

## ADDED Requirements

### Requirement: Seed Can Be Set Before Embark

The game bridge SHALL expose a `set_seed` action for a not-yet-started singleplayer or host run.

#### Scenario: Singleplayer character selection accepts a seed

- **GIVEN** the current screen is `CHARACTER_SELECT`
- **AND** the local lobby is singleplayer and not ready
- **WHEN** the client sends `set_seed` with a non-empty seed string
- **THEN** the Mod updates the `StartRunLobby.Seed` state without calling the standard-mode-unsupported UI notification
- **AND** the returned state exposes the same value at `character_select.seed`

#### Scenario: Existing run cannot have its seed changed

- **WHEN** the client sends `set_seed` outside eligible character selection
- **THEN** the Mod rejects the request with a structured invalid-action error
- **AND** it does not alter any active run

### Requirement: CLI Supports Explicit Seed Bootstrap

The runtime CLI SHALL accept `--seed` for a new run bootstrap without using debug actions.

#### Scenario: CLI starts from main menu

- **GIVEN** `--seed` is supplied and main menu exposes `open_character_select`
- **WHEN** the runtime starts
- **THEN** it opens character selection, sets the requested seed, and begins normal policy execution
