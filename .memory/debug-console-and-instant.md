# 工作台控制台与 Instant

## 适用场景

在本地开发或复现问题时，希望通过工作台 Mod 的 `run_console_command` 执行
`instant`、切换房间或生成测试状态。

## 已验证事实

- `instant` 是工作台的控制台命令，不是普通游戏动作。
- Runtime 通过 Mod API 的 `run_console_command("instant")` 调用它。
- Mod 默认禁用该开发接口；只有游戏进程启动时环境中已有
  `STS2_ENABLE_DEBUG_ACTIONS=1`，接口才可用。
- 通过普通 Steam 方式启动后，再在终端设置该变量不会解锁已经运行的游戏。

## 正确操作

1. 完全退出正在运行的 STS2。
2. 使用 Runtime 的 `--launch-debug-session`，或以等价方式在启动 Steam/STS2 前传入
   `STS2_ENABLE_DEBUG_ACTIONS=1`。
3. 等待 `/health` 成功，再执行 `run_console_command("instant")`。
4. 即使已经启用 `instant`，每个游戏动作后仍要等待状态稳定并重新读取 state；抽牌、
   消耗、敌人死亡和切屏都会改变合法动作。

## 常见误判

当调用返回 HTTP 409，且信息包含 `run_console_command is disabled`：

- 这不是 MCP 服务不可达。
- 这不是 Mod 未加载。
- 这不是普通 `act` 游戏动作不可用。
- 原因是当前游戏不是以 debug session 启动；退出并重启游戏后再试。
