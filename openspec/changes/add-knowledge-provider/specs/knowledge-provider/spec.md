# Delta for Knowledge Provider

## ADDED Requirements

### Requirement: Knowledge Is Retrieved From State IDs

KnowledgeProvider SHALL retrieve knowledge using IDs from the latest
`GameStateSnapshot`.

#### Scenario: Combat state contains enemy IDs

- **GIVEN** a combat state with one or more `enemy_id` values
- **WHEN** KnowledgeProvider builds context
- **THEN** it returns compact monster entries for those IDs

#### Scenario: Event state contains an event ID

- **GIVEN** an event state with an `event_id`
- **WHEN** KnowledgeProvider has a matching curated event entry
- **THEN** it returns the compact event entry for that ID
- **AND** it does not substitute a similarly named event

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
- **AND** the returned source includes a repository-relative `knowledge_path`

### Requirement: LLM Prompt Separates Static Knowledge From Live State

The Runtime SHALL construct the LLM input as ordered messages so curated knowledge
precedes the state that changes every decision.

#### Scenario: Combat decision has retrieved monster knowledge

- **GIVEN** a combat snapshot and compact monster entries from KnowledgeProvider
- **WHEN** OpenAICompatiblePolicy asks the LLM for a decision
- **THEN** it sends stable system rules, a screen contract, a canonical knowledge packet, and dynamic decision state in that order
- **AND** the knowledge packet is encoded before current legal actions and live state

#### Scenario: Equivalent lookup facts arrive in different entity orders

- **GIVEN** two KnowledgeContexts that contain the same entries in different list order
- **WHEN** PromptBuilder builds their knowledge packets
- **THEN** their `knowledge_packet_hash` values are identical

#### Scenario: Provider reports prompt-cache usage

- **WHEN** an OpenAI-compatible response includes `prompt_tokens_details.cached_tokens`
- **THEN** Runtime preserves it in the LLM usage metrics
- **AND** it does not infer a cache hit solely from matching hashes
