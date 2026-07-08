# OpenSpec Agent Instructions

Use the official OpenSpec workflow for this repository:

- Read `openspec/project.md` before creating or modifying specs.
- Treat `openspec/specs/` as the current contract source of truth.
- Put proposed changes under `openspec/changes/<change-id>/`.
- Use `proposal.md` for why/what/impact.
- Use `specs/<capability>/spec.md` for ADDED/MODIFIED/REMOVED requirement deltas.
- Use `design.md` for technical approach and tradeoffs.
- Use `tasks.md` for implementation and verification checklists.

When editing specs:

- Use `### Requirement: ...` headings.
- Use `#### Scenario: ...` headings.
- Use bold `GIVEN`, `WHEN`, `THEN`, and `AND` keywords in scenarios.
- Keep specs behavior-first. Put implementation mechanics in design files.
- Do not assume the runtime will be Codex or Claude Code; the team plans to
  build a dedicated agent runner.

