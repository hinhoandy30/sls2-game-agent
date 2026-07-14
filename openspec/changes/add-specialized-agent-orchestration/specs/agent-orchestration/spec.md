# Delta for Specialized Agent Orchestration

## ADDED Requirements

### Requirement: Runtime Retains Exclusive Game Control

Specialized agents SHALL return decisions only; AgentRuntime remains the sole caller of live game I/O.

#### Scenario: A specialized agent chooses an action

- **WHEN** RouteStrategyAgent, CombatAgent, or RunDevelopmentAgent returns a decision
- **THEN** AgentRuntime validates it against the latest state before execution
- **AND** the agent does not call MCP, HTTP, or game tools directly

### Requirement: Deterministic Screen Routing Selects A Specialist

AgentOrchestrator SHALL select the owning specialist from the latest screen without an LLM routing call.

#### Scenario: Map screen is actionable

- **WHEN** the latest state screen is `MAP`
- **THEN** AgentOrchestrator selects RouteStrategyAgent

#### Scenario: Development screen is actionable

- **WHEN** the latest state screen is `REWARD`, `CARD_SELECTION`, `EVENT`, `SHOP`, `REST`, or `CHEST`
- **THEN** AgentOrchestrator selects RunDevelopmentAgent

### Requirement: Shared Context Is Factual And Versioned

RunContextStore SHALL derive deck facts from fresh game state and expose a versioned strategic plan.

#### Scenario: The deck changes

- **WHEN** a fresh state has a different deck/relic/potion signature
- **THEN** DeckAssessment receives a new signature
- **AND** subsequent specialist prompts receive the new assessment

### Requirement: Historical Experience Is Scoped Advice

Review-generated lessons SHALL be stored separately from curated game facts and retrieved only when their scope matches.

#### Scenario: A prior loss produces a lesson

- **WHEN** RunReviewAgent identifies an evidence-backed strategic mistake
- **THEN** it writes an `ExperienceLesson` with source run/segment/step evidence and `provisional` status
- **AND** it does not modify the curated game fact files

#### Scenario: A later decision matches a lesson scope

- **WHEN** a new state matches an active or provisional experience scope
- **THEN** the applicable lesson is included as labeled historical advice
- **AND** live state and legal actions remain authoritative

### Requirement: GAME_OVER Produces A Review Artifact

Runtime SHALL attempt a non-blocking review after a game-over run when a review agent is configured.

#### Scenario: Review succeeds

- **WHEN** the run terminates on `GAME_OVER` and RunReviewAgent returns valid JSON
- **THEN** Runtime writes `review.json`, persists its lessons, and records the artifact in RunSummary

#### Scenario: Review fails

- **WHEN** the review call or JSON validation fails
- **THEN** Runtime still writes RunSummary
- **AND** it records the review error without changing the completed run result
