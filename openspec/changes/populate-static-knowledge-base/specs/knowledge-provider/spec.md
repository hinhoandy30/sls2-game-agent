# Delta for Knowledge Provider Static Content

## ADDED Requirements

### Requirement: Static Knowledge Entries Cover Core Runtime IDs

The knowledge base SHALL provide schema-valid static entries for known card,
event, and monster runtime IDs without changing the KnowledgeProvider runtime
contract.

#### Scenario: Current state references a known card ID

- **GIVEN** a `GameStateSnapshot` references a known `card_id`
- **WHEN** KnowledgeProvider loads static knowledge
- **THEN** `mcp_server/data/knowledge/v1/cards/<CARD_ID>.json` exists when the card is part of the populated source set
- **AND** the entry uses `card_id` matching the filename
- **AND** the entry contains Chinese human-facing facts and non-local source references

#### Scenario: Current state references a known event ID

- **GIVEN** a `GameStateSnapshot` references a known `event_id`
- **WHEN** KnowledgeProvider loads static knowledge
- **THEN** `mcp_server/data/knowledge/v1/events/<EVENT_ID>.json` exists when the event is part of the populated source set
- **AND** the entry uses `event_id` matching the filename
- **AND** the entry records event facts or options where available without policy recommendations

#### Scenario: Current state references a known enemy ID

- **GIVEN** a `GameStateSnapshot` references a known `enemy_id`
- **WHEN** KnowledgeProvider loads static knowledge
- **THEN** `mcp_server/data/knowledge/v1/monsters/<ENEMY_ID>.json` exists when the monster is part of the populated source set
- **AND** the entry uses `enemy_id` matching the filename
- **AND** the entry records monster facts, moves, or behavior patterns where available without policy recommendations

### Requirement: Static Knowledge Content Remains Auditable

Static knowledge entries SHALL be committed as curated repository JSON and SHALL
not depend on local crawl files at runtime.

#### Scenario: Knowledge content is validated for contribution

- **WHEN** `uv run sts2-validate-knowledge` is executed from `mcp_server`
- **THEN** all populated card, event, and monster JSON entries pass their v1 schemas
- **AND** committed source references do not use `file:///`, `local-crawl`, or developer-local paths

#### Scenario: Generated source data was used during authoring

- **GIVEN** local crawl data was used to generate entries
- **WHEN** the knowledge content is committed
- **THEN** raw crawl files and one-off generator scripts are not required by runtime lookup
- **AND** the committed entries retain stable external source references for audit
