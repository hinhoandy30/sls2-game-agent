# Proposal: Add Agent Runtime Loop

## Why

The project needs a dedicated runner that can drive STS2 without relying on
Codex skills or manual curl calls. Runtime must own game I/O and provide stable
state/action boundaries to Policy, Knowledge, and Evaluation.

## What Changes

**Runtime loop**
- From: Humans or ad-hoc scripts call `/state`, `/action`, and MCP tools.
- To: A dedicated Runtime loop reads state, routes by screen, asks Policy for a
  decision, validates the action, executes it, waits for actionable state, and
  repeats.
- Reason: The team needs a stable foundation for automated runs.
- Impact: Adds the first runner module and establishes Runtime as the only live
  game I/O owner.

**Action validation**
- From: Action legality is enforced mostly by the Mod after a request is sent.
- To: Runtime rejects stale or unavailable actions before calling the live game.
- Reason: Invalid actions should be prevented and logged early.
- Impact: Policy must return `AgentAction` objects that match the latest state.

## Impact

- Runtime team can start implementation.
- Policy can remain independent and return `PolicyDecision`.
- Evaluation can consume records emitted by Runtime after each attempted action.

