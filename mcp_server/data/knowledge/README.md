# STS2 中文知识库

这里是专用 Agent Runtime 使用的、按游戏内部 ID 检索的中文静态知识库。第一版使用 JSON，
原因是 Runtime 可以用 Pydantic 严格校验字段，并且只读取当前局面需要的单个文件。

```text
data/knowledge/v1/
  monsters/<ENEMY_ID>.json
  events/<EVENT_ID>.json
  cards/<CARD_ID>.json
  strategy/card_priorities/<CARD_ID>.json
```

`cards/` 是卡牌事实库：费用、类型、效果、升级变化、关键词等可验证机制。
`strategy/card_priorities/` 是条件化策略知识：什么时候优先拿、什么时候跳过、升级优先级。
不要把这两类混在一起；事实库不写“应该选”，策略库不改写游戏机制事实。

## 维护规则

1. 文件名必须与 Mod state 中的 `enemy_id` 或 `event_id` 完全一致。
2. 所有说明文字使用中文；内部 ID、来源 URL 和 schema 字段保留英文。
3. 每个事实都要有 `sources`。游戏更新后，先核对来源和版本，再修改对应文件。
4. 写可验证的机制事实，例如招式、伤害、状态牌、固定循环和阈值；不要写“应该选 X”这类策略结论。
5. 当前回合的精确伤害、攻击次数、实际可选事件选项以 live state 为准：
   `combat.enemies[].intents` 和 `event.options` 的优先级高于这里的静态资料。
6. JSON 只应保存紧凑资料。长篇复盘、策略实验和不确定观察写入 `agent_knowledge/run_logs/`，
   经人工核验后再提炼进本目录。

复制 `monsters/_template.json` 或 `events/_template.json` 后改名，即可新增一条知识。Runtime
只会按当前 ID 读取文件，以下划线开头的模板不会被加载。

可复制的模板：

- `monsters/_template.json`
- `events/_template.json`
- `cards/_template.json`
- `strategy/card_priorities/_template.json`

## 组员协作入口

日常派活使用 GitHub Issues，不靠手动维护长文档：

1. Owner 创建 `Knowledge entry - monster`、`Knowledge entry - event`、`Knowledge entry - card` 或
   `Strategy entry - card priority` issue，并填写 ID、中文名、范围和来源。
2. 组员从 issue 新建分支，只改对应 JSON 文件。
3. 提 PR 前运行：

```bash
cd mcp_server
uv run sts2-validate-knowledge
```

4. PR 关联 issue，review 重点看事实是否可验证、来源是否可靠、字段是否紧凑。
