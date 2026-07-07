# Tasks: Define Agent Collaboration Contracts

## 1. Contract Acceptance

- [ ] Review `openspec/specs/agent-collaboration-contracts/spec.md` with all
      team leads.
- [ ] Confirm whether first runner uses MCP guided tools or direct HTTP.
- [ ] Confirm JSON schema filenames and fixture locations.
- [ ] Record accepted changes in the project planning document.

## 2. Runtime Work

- [ ] Implement `GameClient.health`.
- [ ] Implement `GameClient.get_state`.
- [ ] Implement `GameClient.act`.
- [ ] Implement `GameClient.wait_until_actionable`.
- [ ] Implement action validation against `available_actions`.
- [ ] Emit `StepRecord` for every attempted action.

## 3. Policy Work

- [ ] Implement `Policy.decide` interface.
- [ ] Implement `CombatPolicyV0` from mock combat fixtures.
- [ ] Implement `MapPolicyV0`.
- [ ] Implement `RewardPolicyV0`.
- [ ] Add tests that assert expected `AgentAction` for fixtures.

## 4. Knowledge Work

- [ ] Implement `KnowledgeProvider.for_state`.
- [ ] Implement card lookup by `card_id`.
- [ ] Implement monster lookup by `enemy_id`.
- [ ] Implement relic, potion, and event lookup stubs.
- [ ] Add caching and source references.

## 5. Evaluation Work

- [ ] Implement `StepRecord` JSONL reader.
- [ ] Implement `RunSummary` writer.
- [ ] Implement metrics for invalid actions, floor reached, damage taken, and
      terminal result.
- [ ] Build reports from mock trajectories before live runtime is ready.

## 6. Fixture Work

- [ ] Add `MAIN_MENU` fixture.
- [ ] Add `CHARACTER_SELECT` fixture.
- [ ] Add `MAP` fixture.
- [ ] Add first `COMBAT` fixture.
- [ ] Add `REWARD` fixture.

