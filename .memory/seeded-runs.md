# 固定种子开局

## 适用场景

需要可复现的评测、回归测试或多人共享同一开局时。

## 已验证事实

- STS2 的 `StartRunLobby` 提供 `SetSeed(string)`；本项目 Mod 的 `set_seed` action 在
  `CHARACTER_SELECT`、本地玩家尚未 ready、且不是多人客户端时可用。
- 在正式版 `v0.107.1` 的标准单人角色选择页，不能调用 `StartRunLobby.SetSeed`：它会先写入值、再调用
  `NCharacterSelectScreen.SeedChanged()`，而后者会抛出 `Seed should not be changed in standard mode!`。
  Mod 必须只写入 `StartRunLobby.Seed` 的非公开 setter；正常 embark 会读取并 canonicalize 这个值。
- Runtime CLI 的 `--seed <seed>` 只在新开局 bootstrap 使用：它从主菜单打开角色选择，设置种子，
  再交给正常的选角/出发流程。
- CLI 默认不会为了设置种子放弃或覆盖已有 run；当前屏幕不满足条件时应报错并由人决定如何处理。
  只有显式传入 `--replace-existing-run`，它才会在主菜单执行 `abandon_run -> confirm_modal` 后创建
  新的固定种子局。

## 正确操作

1. 结束、放弃或返回已有 run，确保可以进入新开局流程。
2. 在实验命令中显式传入 `--seed`，并同时记录角色、难度、模型、Mod 和 Runtime 版本。
3. 读取 fresh state，确认 `character_select.seed` 回显目标 seed 后再 embark。

## 实机验证（2026-07-13）

- 从无续局主菜单执行 `--launch-debug-session --seed HYPF24C3XC --max-steps 0` 成功返回。
- Runtime 的回显校验通过，终态为 `CHARACTER_SELECT`、`error_count = 0`；日志中 `set_seed` 的
  `POST /action` 返回 HTTP 200。
- `--max-steps 0` 是只验证 bootstrap 的推荐方式：它不会选择角色或开始游玩。
