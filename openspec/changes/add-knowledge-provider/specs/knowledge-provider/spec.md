# Delta for Knowledge Provider

## ADDED Requirements

### Requirement: Knowledge Is Retrieved From State IDs

KnowledgeProvider SHALL retrieve knowledge using IDs from the latest
`GameStateSnapshot`.

#### Scenario: Combat state contains enemy IDs

- **GIVEN** a combat state with one or more `enemy_id` values
- **WHEN** KnowledgeProvider builds context
- **THEN** it returns compact monster entries for those IDs

### Requirement: KnowledgeContext Is Compact

KnowledgeProvider SHALL return compact entries suitable for Policy decisions.

#### Scenario: Full docs are available

- **GIVEN** full markdown docs and JSON exports are available
- **WHEN** KnowledgeProvider returns context for one decision
- **THEN** it includes only relevant summaries and fields
- **AND** it does not include entire markdown files by default

### Requirement: Knowledge Includes Sources

KnowledgeProvider SHALL include source references for returned facts.

#### Scenario: Static data fact is returned

- **WHEN** KnowledgeProvider returns a card or monster entry
- **THEN** the entry includes a source reference to the data file or doc section

