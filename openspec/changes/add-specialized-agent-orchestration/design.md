# Design: 专项 Agent 编排与复盘经验闭环

## 控制边界

```text
AgentRuntime -> AgentOrchestrator -> specialized Policy -> PolicyDecision
     |                                                        |
     +--- validate / HTTP action / wait / trajectory <--------+
```

Runtime 是唯一 live game I/O 所有者。Orchestrator 仅做确定性 screen 路由：

| Screen | Owner |
| --- | --- |
| MAP | RouteStrategyAgent |
| COMBAT | CombatAgent |
| REWARD / CARD_SELECTION / EVENT / SHOP / REST / CHEST | RunDevelopmentAgent |
| MAIN_MENU / CHARACTER_SELECT / MODAL | existing deterministic policy |
| GAME_OVER | Runtime triggers RunReviewAgent after run loop ends |

RouteStrategyAgent 维护长期目标并选择当前地图节点，第一版不把这两个紧密耦合的职责拆成互相
调用的 LLM。

## Shared Context

`RunContextStore` 从每个 fresh `GameStateSnapshot` 派生事实：

- `DeckAssessment`：完整卡组的按 ID 聚合、升级数、卡牌类型数、诅咒数、遗物、药水和稳定 signature；
- `StrategicPlan`：由路线/发展 agent 以受限 schema 更新的风险预算、路线偏好、获取优先级和回避条件；
- `ExperienceContext`：由当前角色、screen、楼层与 deck tags 检索到的有限历史经验。

DeckAssessment 的数值由代码计算，LLM 不可覆盖。StrategicPlan 更新只能是 JSON schema 允许的策略
字段，且会带版本和基于的 deck signature。

## Prompt Layout

专项 agent 的请求从稳定到动态依次为：

1. agent-specific system rules；
2. screen response contract；
3. run context packet（deck assessment、strategic plan、applicable experiences）；
4. curated game knowledge packet；
5. current live state and legal actions。

经验条目不是游戏事实。提示词必须声明：live state 与 legal actions 优先；经验只是在适用条件下的
可反驳建议。Combat 的 action plan 仍仅使用 stable `legal_action_id`。

## Experience Lifecycle

```text
GAME_OVER trajectory + contexts
  -> RunReviewAgent
  -> review.json + ExperienceLesson(status=provisional)
  -> agent_knowledge/experience/v1/lessons/*.json
  -> ExperienceRetriever (scoped, top-k)
  -> next run's Route/Combat/Development prompt
```

每条 lesson 必须含 run/segment/step evidence、scope、recommendation、counterexamples、confidence
和 status。`provisional` 可以作为低优先级提醒；团队人工审核或多局证据后可升级为 `active`。
Review 失败不能影响已经结束的 run，也不能阻止 summary 落盘。

## Observability And Fallback

每个 decision metadata 记录 agent name、deck signature、strategy plan version、检索到的
experience IDs 和任何 strategy update。Runtime 同时写 `context.jsonl`。LLM 调用失败时沿用已有
错误记录边界；不由其他 agent 静默替代或绕过 validation。
