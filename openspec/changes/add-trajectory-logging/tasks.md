# Tasks: Add Trajectory Logging

## 1. Schemas

- [x] Define `StepRecord`.
- [x] Define `RunSummary`.
- [x] Define compact `state_summary`.
- [x] Define `TrajectorySegment`、`state_hash_before` 和 `state_hash_after`，用于标识 checkpoint 回退分支。

## 2. Logger

- [x] Implement append-only JSONL writer.
- [x] Implement summary writer.
- [x] Add run directory creation.
- [x] Include game version when available.
- [ ] Include repo commit in every record。（当前 `StepRecord` 尚未写入 commit；不要误以为已实现。）
- [x] 写入 `segments.jsonl`，并在同一 Runtime 进程内检测 `continue_run` 后的 checkpoint 回退。
- [x] 在 `RunSummary` 写入 `duration_seconds`、`token_usage` 和 `segment_count`。

## 3. Evaluation Fixtures

- [ ] Add a mock first-combat trajectory.
- [ ] Add a failed-action trajectory.
- [ ] Add a completed-reward trajectory.

## 4. Verification

- [ ] Add parser tests for JSONL logs.
- [x] Add summary metric tests for duration, token usage, state hashes, and segment count.
- [ ] Run `openspec validate --all`。（当前开发 shell 未找到 `openspec` CLI；上传前需按 README 安装/恢复该命令后执行。）
