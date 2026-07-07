# Project Context

## Goal

Build a dedicated Slay the Spire 2 agent runner on top of the existing
`STS2AIAgent` Mod and MCP/HTTP API. The runner should eventually optimize for
stable progression and win streaks, but the first milestone is reliable,
auditable gameplay through early runs.

## Current Base

- Game bridge: `STS2AIAgent` C# Mod exposes `/health`, `/state`,
  `/actions/available`, `/action`, `/data/*`, and `/events/stream`.
- MCP wrapper: `mcp_server` exposes guided tools such as `get_game_state`,
  `act`, `wait_until_actionable`, and game-data lookups.
- Recommended gameplay contract: use the compact guided state first; raw state
  is for debugging only.
- Verified locally on macOS against STS2 `v0.107.1` through first combat reward.

## Team Principles

- Interfaces before implementation.
- Runtime does not own game strategy.
- Policy does not directly call the game API.
- Knowledge retrieval does not execute actions.
- Evaluation consumes logs and summaries only; it should not need a live game.
- Every live run must be reproducible enough to diagnose invalid actions,
  crashes, and bad policy choices.

