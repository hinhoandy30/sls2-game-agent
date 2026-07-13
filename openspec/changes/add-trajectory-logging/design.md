# Design: Trajectory Logging

## Output Shape

Runtime writes:

```text
runs/<date>/<run-id>/
  trajectory.jsonl
  segments.jsonl
  summary.json
```

## StepRecord

Each JSONL line should include:

- schema version
- run id
- step id
- timestamp
- repo commit
- game version
- screen and floor
- state summary
- knowledge references
- policy decision
- action request
- action result
- metrics delta
- error, if any

已实现的额外字段：

- `segment_id`：该 step 属于哪一条 checkpoint 分支；
- `state_hash_before` / `state_hash_after`：紧凑稳定状态摘要的 hash，用于识别
  `continue_run` 是否回到存档点；
- `metrics.step_duration_seconds`：本 step 的 wall-clock 用时；
- 若 decision 来自 LLM，`decision.metadata.llm` 可包含请求耗时和 provider usage。

`segments.jsonl` 一行对应一个 `TrajectorySegment`。Runtime 启动时创建第一个 segment；若同一
Runtime 进程里的 `continue_run` 前后 hash 不同，则创建 `retry_from_checkpoint` 子 segment。
这能防止把“从战斗起点重打”错误地当作同一条线性 trajectory 的后续回合。跨进程、跨输出目录的
run 目前不会自动关联，Evaluation 不能据此推断它们一定是同一个存档。

## RunSummary

The summary should include:

- seed
- character
- ascension
- start/end time
- final result
- floor reached
- invalid action count
- recoverable error count
- terminal reason

当前实现还包括：

- `duration_seconds`：整个 Runtime wall-clock 时间；
- `token_usage`：LLM provider 在响应中返回 usage 时的汇总；
- `segment_count`：本次 Runtime 进程记录的 segment 数。

## Privacy and Size

Logs should avoid full raw state by default. Store compact state summaries and
IDs; capture raw payloads only when debug logging is explicitly enabled.
