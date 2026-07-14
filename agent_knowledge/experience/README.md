# 复盘经验知识库

这里保存 `RunReviewAgent` 在失败对局后生成的**策略经验**，与
`mcp_server/data/knowledge/v1/` 的游戏事实资料完全分开。

目录：

```text
agent_knowledge/experience/v1/lessons/<lesson_id>.json
```

每条经验必须通过 `ExperienceLesson` Pydantic schema，含可追溯的 run、segment、step evidence、
适用范围、反例和置信度。默认写入 `provisional`；它只会作为明确标记的历史建议进入后续 prompt。
人工审核或多局独立证据支持后，可将 `status` 改为 `active`。`rejected` 不会被检索。

不要在这里写怪物固定伤害、卡牌文本或事件效果；这些游戏事实属于 `mcp_server/data/knowledge/v1/`。
