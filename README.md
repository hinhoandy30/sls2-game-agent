# SLS2 Game Agent

`sls2-game-agent` is a team project for building a dedicated AI agent that can
play Slay the Spire 2 through a structured game API. The current repository
contains:

- a C# STS2 Mod that exposes game state and actions through local HTTP;
- a Python MCP wrapper for AI clients;
- OpenSpec contracts for team collaboration;
- local macOS adaptation notes for STS2 `v0.107.1`;
- the first planning artifacts for a dedicated agent runner.

## Attribution

This repository is not a from-scratch original project. It is developed from the
upstream open-source project
[CharTyr/STS2-Agent](https://github.com/CharTyr/STS2-Agent), which provided the
Mod, MCP server, scripts, and documentation foundation.

Do not describe this repository as fully original work. Keep the existing
license and upstream-origin history visible, and preserve attribution to the
upstream project in public releases, forks, and derived documentation.

License: AGPL-3.0-only. See [LICENSE](./LICENSE).

Project notice: [NOTICE.md](./NOTICE.md).

## Repository Status

Verified locally:

- macOS Apple Silicon;
- Steam Slay the Spire 2 `v0.107.1`;
- game runtime `MegaDot/Godot 4.5.1` Mono custom build;
- Mod loads and exposes `http://127.0.0.1:8080/health`;
- HTTP control chain reached: main menu -> Ironclad -> first combat -> reward.

Detailed local adaptation record:

- [docs/macos-v0.107.1-local-adaptation.md](./docs/macos-v0.107.1-local-adaptation.md)

## Install Slay the Spire 2

Install Slay the Spire 2 through Steam first.

Common paths:

```text
macOS:
~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2

Windows:
C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2
```

For the current team baseline, use STS2 `v0.107.1`. If Steam updates the game,
the C# Mod may need another compatibility pass before the agent can run safely.

## Install Local Tooling

### .NET 9 SDK

The Mod is built with .NET 9. On this machine we used a local SDK install:

```bash
curl -sSL https://dot.net/v1/dotnet-install.sh -o /private/tmp/dotnet-install.sh
bash /private/tmp/dotnet-install.sh --channel 9.0 --install-dir /Users/liuzhen/Documents/sls2/.dotnet
```

Shell environment:

```bash
export PATH="/Users/liuzhen/Documents/sls2/.dotnet:$PATH"
export DOTNET_CLI_HOME="/Users/liuzhen/Documents/sls2/.dotnet-home"
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
```

### Godot / MegaDot

No standalone Godot editor is required for normal Mod build and validation.
STS2 ships its own `MegaDot/Godot 4.5.1` Mono runtime and data assemblies.

### Python and uv

Install `uv` for the MCP server:

```bash
brew install uv
```

Then:

```bash
cd mcp_server
uv sync
uv run pytest
```

### OpenSpec

OpenSpec is used for team contracts and planning.

Recommended team install:

```bash
npm install -g @fission-ai/openspec@latest
```

This workspace also has a checked-out official OpenSpec source tree at:

```text
/Users/liuzhen/Documents/sls2/OpenSpec-main
```

If the global `openspec` command is not available, use:

```bash
node /Users/liuzhen/Documents/sls2/OpenSpec-main/bin/openspec.js validate --all
```

OpenSpec files for this project live under:

```text
openspec/
```

Current shared contract:

- [openspec/specs/agent-collaboration-contracts/spec.md](./openspec/specs/agent-collaboration-contracts/spec.md)

## Build and Install the Mod

Set the STS2 data directory on macOS:

```bash
export STS2_DATA_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"
```

Build the Mod:

```bash
dotnet build STS2AIAgent/STS2AIAgent.csproj -c Release
```

Install it into the local Steam game:

```bash
./scripts/build-mod.sh \
  --configuration Release \
  --game-root "$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2"
```

The macOS install target is:

```text
SlayTheSpire2.app/Contents/MacOS/mods/
  STS2AIAgent.dll
  STS2AIAgent.pck
  STS2AIAgent.json
```

## Enable and Verify the Mod

Start STS2, then verify:

```bash
curl -s http://127.0.0.1:8080/health
```

Expected result includes:

```json
{
  "service": "sts2-ai-agent",
  "game_version": "v0.107.1",
  "status": "ready"
}
```

For a scripted smoke test:

```bash
./scripts/test-mod-load.sh \
  --game-root "$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2"
```

## Start the MCP Server

Default stdio MCP:

```bash
./scripts/start-mcp-stdio.sh
```

Network MCP:

```bash
./scripts/start-mcp-network.sh
```

Default network endpoint:

```text
http://127.0.0.1:8765/mcp
```

For normal agent development, prefer the guided MCP surface:

- `health_check`
- `get_game_state`
- `act`
- `wait_until_actionable`
- `get_relevant_game_data`

## Team Collaboration

Enterprise-style workflow documentation:

- [docs/team-workflow.md](./docs/team-workflow.md)
- [.github/CONTRIBUTING.md](./.github/CONTRIBUTING.md)
- [.github/pull_request_template.md](./.github/pull_request_template.md)

Short version:

```text
idea -> OpenSpec change -> spec review -> implementation PR -> validation -> archive
```

Rules:

- `main` is the protected release branch.
- `dev` is the integration branch.
- Feature branches merge into `dev`.
- Cross-team contracts must be described in OpenSpec before implementation.
- Runtime, Policy, Knowledge, Evaluation, and Mod/API boundaries are defined in
  `agent-collaboration-contracts`.

## MVP0

MVP0 is the dedicated runner foundation. The first planned work items are:

1. `add-agent-runtime-loop`
2. `add-trajectory-logging`
3. `add-knowledge-provider`
4. `add-combat-policy-v0`

These changes should let the team build a first runner that can read live state,
choose legal actions, log every step, retrieve compact knowledge, and make
basic combat decisions against fixtures before full live integration.

## Repository Layout

- `STS2AIAgent/`: C# game Mod source.
- `mcp_server/`: Python FastMCP wrapper and game-data exports.
- `scripts/`: build, startup, and validation helpers.
- `docs/`: setup, workflow, troubleshooting, and game knowledge docs.
- `openspec/`: team contracts and change plans.
- `skills/`: optional Codex/AI-client skill instructions from the upstream
  project. The dedicated runner should not depend on these at runtime.
