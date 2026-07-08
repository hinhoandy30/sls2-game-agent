# Team Workflow

This project uses GitHub for code collaboration and OpenSpec for team-facing
contracts.

## Owner Setup

The repository owner should configure GitHub once:

1. Set `dev` as the default branch after it is pushed.
2. Protect `main`.
3. Require pull requests before merging to `main`.
4. Prefer feature PRs into `dev`.
5. Promote `dev` to `main` only after validation.

Recommended branch protection:

- `main`: no direct pushes, require PR review, require status checks once CI
  exists.
- `dev`: allow normal PR merges, optionally require one review.

## Working Model

Use this sequence for cross-team work:

```text
idea -> OpenSpec change -> spec review -> implementation PR -> validation -> archive
```

Small local fixes may skip a new OpenSpec change when they do not alter team
contracts, public behavior, or shared schemas.

## First Four Changes

Start with these OpenSpec changes:

1. `add-agent-runtime-loop`
   - Owner: Runtime
   - Purpose: connect to the game API, route screens, validate actions.
2. `add-trajectory-logging`
   - Owner: Evaluation
   - Purpose: define and write `StepRecord` JSONL and `RunSummary`.
3. `add-knowledge-provider`
   - Owner: Knowledge
   - Purpose: retrieve compact card, monster, relic, potion, and event context.
4. `add-combat-policy-v0`
   - Owner: Policy
   - Purpose: decide basic combat actions from fixture state plus knowledge.

These can run in parallel because the shared contracts are defined in
`openspec/specs/agent-collaboration-contracts/spec.md`.

## GitHub Issues

Create one issue per OpenSpec change.

Issue format:

```markdown
OpenSpec change:
openspec/changes/<change-id>

Owner:
Runtime / Policy / Knowledge / Evaluation / Mod/API

Depends on:
agent-collaboration-contracts

Done when:
- openspec validate --all passes
- implementation PR is merged
- tests or fixture checks are included
```

## Pull Requests

Use two PRs for medium or large work:

1. Spec PR: adds or updates `openspec/changes/<change-id>/`.
2. Implementation PR: code, fixtures, docs, and verification.

Small changes may combine spec and implementation in one PR when the contract is
obvious and the affected teams agree.

## Daily Routine

Before starting work:

```bash
git pull
openspec list
openspec show agent-collaboration-contracts --type spec
```

Before opening a PR:

```bash
openspec validate --all
git status
```

If OpenSpec is not globally installed, use:

```bash
node /Users/liuzhen/Documents/sls2/OpenSpec-main/bin/openspec.js validate --all
```

