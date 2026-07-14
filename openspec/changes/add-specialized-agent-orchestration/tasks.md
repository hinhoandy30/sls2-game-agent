# Tasks: 专项 Agent 编排与复盘经验闭环

## 1. Contracts And Context

- [x] 定义并验证 DeckAssessment、StrategicPlan、ExperienceLesson、ReviewReport schema。
- [x] 实现从 fresh state 计算 deck signature 与 DeckAssessment。
- [x] 实现 RunContextStore、战略计划受限更新与 context snapshot。

## 2. Experience Knowledge

- [x] 实现经验 JSON repository、scope matching、top-k 检索和去重。
- [x] 创建 `agent_knowledge/experience/v1/` 维护说明与 lesson 模板。
- [x] 明确区分 curated game facts 与 review-generated strategy experience。

## 3. Specialized Online Agents

- [x] 扩展 LLM prompt builder，加入可缓存的 run context packet 与 agent metadata。
- [x] 实现 RouteStrategyAgent 并绑定 MAP。
- [x] 实现 CombatAgent 并绑定 COMBAT stable action plans。
- [x] 实现 RunDevelopmentAgent 并绑定奖励、选牌、事件、商店、休息和宝箱。
- [x] 实现确定性 AgentOrchestrator，并保留非 gameplay screen 的安全 fallback policy。

## 4. Review And Runtime Integration

- [x] 实现 RunReviewAgent，生成结构化失败复盘与经验条目。
- [x] Runtime 写 context.jsonl，并在 GAME_OVER 后执行 review、写 review.json 和经验文件。
- [x] 扩展 CLI 的 multi-agent policy 与 review/experience 参数。

## 5. Verification

- [x] 为 context、经验匹配、各 screen 路由、战略更新和 review fixture 添加单元测试。
- [x] 为 Runtime 记录 agent metadata 与 game-over review 添加 fixture 测试。
- [x] 将 release session 的 `instant` debug-action 拒绝显示为可操作的启动提示，并保留 HTTP 错误体。
- [x] 对语法正确但为空/非法的 Combat action plan 进行一次受限语义修复，避免将其直接记为 policy error。
- [x] 运行 unittest、OpenSpec validate 和 wheel 内容检查。（2026-07-13：69 tests；OpenSpec 10 passed；wheel 已确认含多 agent 模块与知识 JSON。）
