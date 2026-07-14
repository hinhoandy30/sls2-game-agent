# Contributing

## Branch workflow

- `main` is the protected release branch.
- `dev` is the default integration branch for ongoing development.
- Open pull requests from feature branches into `dev`.
- Open pull requests from `dev` into `main` when preparing a release or promoting tested changes.
- Do not push directly to `main`.

Recommended branch naming:

- `codex/<topic>`
- `feat/<topic>`
- `fix/<topic>`
- `chore/<topic>`

## OpenSpec workflow

Cross-team work should start with an OpenSpec change before implementation.
This is required when a change affects Runtime, Policy, Knowledge, Evaluation,
or the Mod/API contract.

Recommended flow:

1. Create a spec branch: `spec/<change-id>`.
2. Add or update `openspec/changes/<change-id>/`.
3. Run OpenSpec validation.
4. Open a PR into `dev` for the spec artifacts.
5. After review, implement on `feat/<change-id>` or `fix/<change-id>`.
6. Link the implementation PR to the OpenSpec change.
7. Archive the change only after implementation and verification are complete.

Useful commands:

```bash
openspec list
openspec list --specs
openspec show agent-collaboration-contracts --type spec
openspec status --change <change-id>
openspec validate --all
```

If `openspec` is not installed globally, use the local checked-out CLI:

```bash
export OPENSPEC_ROOT="$HOME/path/to/OpenSpec"
node "$OPENSPEC_ROOT/bin/openspec.js" validate --all
```

## Validation expectations

For OpenSpec changes:

- Run `openspec validate --all`
- Confirm affected teams reviewed the relevant contract

For mod changes:

- Run `dotnet build "STS2AIAgent/STS2AIAgent.csproj"`
- Run `powershell -ExecutionPolicy Bypass -File "scripts/build-mod.ps1"`
- Run `powershell -ExecutionPolicy Bypass -File "scripts/test-mod-load.ps1"`

For MCP server changes:

- Run `cd "mcp_server"` then `uv sync`
- Run `uv run sts2-mcp-server`
- Verify the server can reach `/health` or `/state` from a running mod

For knowledge-base changes:

- Use a GitHub issue from `Knowledge entry - monster`, `Knowledge entry - event`,
  `Knowledge entry - card`, or `Strategy entry - card priority` as the assignment unit.
- Edit only the matching JSON file under `mcp_server/data/knowledge/v1/`.
- Keep text in Chinese, but keep runtime IDs and schema fields in English.
- For `monsters/`, `events/`, and `cards/`, record verifiable facts, not policy advice.
- For `strategy/`, record conditional strategy advice with clear good/bad conditions.
- Run `cd "mcp_server"` then `uv run sts2-validate-knowledge`.

## Release flow

1. Merge tested work into `dev`.
2. Validate release candidates from `dev`.
3. Open a `dev -> main` pull request.
4. Merge to `main` after final review.
5. Tag and publish the release from `main`.
