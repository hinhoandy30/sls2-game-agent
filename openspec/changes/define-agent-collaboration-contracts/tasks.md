# Tasks: Define Agent Collaboration Contracts

## 1. Contract Acceptance

- [ ] Review `openspec/specs/agent-collaboration-contracts/spec.md` with all
      team leads.
- [x] Confirm whether first runner uses MCP guided tools or direct HTTP.（MVP0 使用直接 HTTP `HttpGameClient`；MCP 保留给人工调试。）
- [ ] Confirm JSON schema filenames and fixture locations.
- [x] Record current implementation status in `openspec/implementation-status.md`。（仍待团队正式评审共享契约。）

## 2. Runtime Work

- [x] Implement `GameClient.health`.
- [x] Implement `GameClient.get_state`.
- [x] Implement `GameClient.act`.
- [x] Implement `GameClient.wait_until_actionable`.
- [x] Implement action validation against `available_actions`.
- [x] Emit `StepRecord` for every attempted action.

## 3. Policy Work

- [x] Implement `Policy.decide` interface.
- [x] Implement `CombatPolicyV0`。（当前基于 in-test mock payload；可运行但不是完整策略。）
- [x] Implement `MapPolicyV0`.
- [x] Implement `RewardPolicyV0`.
- [x] Add tests that assert expected `AgentAction` for mock states.

## 4. Knowledge Work

- [x] Implement `KnowledgeProvider.for_state`。（当前仅提取 monster/card/potion refs，不进行资料查询。）
- [ ] Implement card lookup by `card_id`.
- [ ] Implement monster lookup by `enemy_id`.
- [ ] Implement relic, potion, and event lookup stubs.
- [ ] Add caching and source references.

## 5. Evaluation Work

- [ ] Implement `StepRecord` JSONL reader.
- [x] Implement `RunSummary` writer in Runtime。（Evaluation 仍缺 JSONL reader 和 metrics/report。）
- [ ] Implement metrics for invalid actions, floor reached, damage taken, and
      terminal result.
- [ ] Build reports from mock trajectories before live runtime is ready.

## 6. Fixture Work

- [ ] Add `MAIN_MENU` fixture.
- [ ] Add `CHARACTER_SELECT` fixture.
- [ ] Add `MAP` fixture.
- [ ] Add first `COMBAT` fixture.
- [ ] Add `REWARD` fixture.
