# Proposal: Add Combat Policy V0

## Why

MVP0 needs a basic combat decision module that can operate against fixture state
and later live state. It does not need to be strong; it needs to be legal,
auditable, and safe enough to extend.

## What Changes

**CombatPolicyV0**
- From: Combat decisions are made manually or by general-purpose reasoning.
- To: A policy module chooses legal combat actions from state plus knowledge.
- Reason: The dedicated runner needs a first autonomous combat policy.
- Impact: Policy team can test combat decisions without live game access.

**Fixture-first tests**
- From: Combat behavior is validated only by live runs.
- To: Basic combat decisions are tested against saved fixtures.
- Reason: Policy work should not block on Runtime.
- Impact: Requires representative combat fixtures.

## Impact

- Runtime can call a stable combat policy interface.
- Evaluation can compare policy decisions across fixture trajectories.
- Future LLM or search-based combat agents can replace V0 behind the same
  interface.

