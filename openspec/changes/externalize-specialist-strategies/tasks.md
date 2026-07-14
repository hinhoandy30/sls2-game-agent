# Tasks

## 1. Strategy data contract

- [x] 1.1 Add a Pydantic strategy schema and versioned provider.
- [x] 1.2 Add default Chinese strategies for combat, route strategy and run development.
- [x] 1.3 Add maintainer documentation and package the strategy directory in wheel/sdist builds.

## 2. Runtime integration

- [x] 2.1 Remove inline specialist strategy strings from the orchestrator.
- [x] 2.2 Load rendered strategy instructions and record ID/revision/content hash in decision metadata.
- [x] 2.3 Add CLI `--strategy-dir` override for isolated experiments.

## 3. Verification

- [x] 3.1 Add tests for loading, rendering and strategy metadata.
- [x] 3.2 Run Python unit tests.
- [x] 3.3 Build the distributable package and verify strategy files are included.
