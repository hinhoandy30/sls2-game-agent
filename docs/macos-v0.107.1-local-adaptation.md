# macOS 适配 STS2 v0.107.1 记录

更新时间：2026-07-07

本文记录从 GitHub 拉取本项目后，在 macOS 上把 STS2AIAgent 修到当前正式版 Slay the Spire 2 `v0.107.1` 可构建、可加载、可通过 MCP/HTTP 读取状态并执行动作的过程。

## 当前结论

- 已验证游戏版本：`v0.107.1`
- 已验证引擎：游戏自带 `MegaDot/Godot 4.5.1` Mono custom build
- 已验证系统：macOS Apple Silicon
- 已验证 Mod 加载：`STS2AIAgent` 可以被游戏加载，并启动 `http://127.0.0.1:8080/`
- 已验证读取状态：`GET /health`、`GET /state`、`GET /actions/available` 可用
- 已验证执行动作：通过 `POST /action` 完成主菜单、角色选择、Neow 奖励、地图选择、战斗出牌
- 已验证最小游戏闭环：从主菜单进入铁甲战士局，选择第一个怪物节点，击杀 `SLUDGE_SPINNER` 后到达奖励页

边界也要说清楚：这次证明了 MCP/HTTP 链路、开局到第一场普通战斗、基础目标选择出牌、结束战斗进入奖励页可用；还没有完整证明奖励选择、事件、商店、篝火、Boss、连胜循环、崩溃恢复全部可靠。后续 agent 开发必须继续按场景补验证。

## 本机路径

项目目录：

```bash
/Users/liuzhen/Documents/sls2/STS2-Agent-main
```

Steam 游戏目录：

```bash
~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2
```

macOS arm64 游戏数据目录：

```bash
~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64
```

游戏可执行文件：

```bash
~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/MacOS/Slay the Spire 2
```

安装后的 Mod 文件：

```bash
~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/MacOS/mods/STS2AIAgent.dll
~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/MacOS/mods/STS2AIAgent.pck
~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/MacOS/mods/STS2AIAgent.json
```

## 从 GitHub 拉取后的准备

如果拿到的是 GitHub zip 包，先初始化 Git 并保存原始版本：

```bash
cd /Users/liuzhen/Documents/sls2/STS2-Agent-main
git init
git add .
git commit -m "Initial STS2 agent project import"
```

如果是正常 clone：

```bash
git clone <repo-url>
cd STS2-Agent-main
```

建议在修正式版前先建分支：

```bash
git switch -c macos-v0.107.1-adaptation
```

## 需要安装或确认的工具

`.NET 9 SDK`：

```bash
curl -sSL https://dot.net/v1/dotnet-install.sh -o /private/tmp/dotnet-install.sh
bash /private/tmp/dotnet-install.sh --channel 9.0 --install-dir /Users/liuzhen/Documents/sls2/.dotnet
```

本项目当前使用本地 SDK，不依赖全局安装：

```bash
export PATH="/Users/liuzhen/Documents/sls2/.dotnet:$PATH"
export DOTNET_CLI_HOME="/Users/liuzhen/Documents/sls2/.dotnet-home"
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
```

Godot/Godot Mono：

- 当前不需要额外安装独立 Godot 编辑器。
- STS2 自带的游戏运行时已经是 `4.5.1` Mono custom build，构建脚本会使用游戏目录里的数据和程序集。

Python/MCP：

```bash
cd mcp_server
uv sync
uv run pytest
```

如果团队希望统一 Python 版本，建议使用 `uv` 管理虚拟环境，而不是依赖 macOS 系统 Python。

## v0.107.1 需要的代码修复

### 1. 游戏 API 字段改名

`STS2AIAgent/Game/GameStateService.cs` 中，当前正式版没有 `player.CanUseOrRemovePotions`，需要改为：

```csharp
player.CanRemovePotions
```

否则 C# Mod 无法通过 `dotnet build`。

### 2. macOS Python 兼容

`scripts/lib-sts2.sh` 内嵌 Python 原本用了 Python 3.10+ 的 `int | None` 写法。macOS 系统 Python 可能是 3.9，会直接语法错误。

修法是改成：

```python
from typing import Optional

def find_process_using_port(port: int) -> Optional[int]:
    ...
```

或者团队统一用 `uv` 提供 Python 3.12+ 来执行验证脚本。

### 3. Mod manifest 安装位置

当前正式版的本地 Mod 加载不仅需要 `.dll` 和 `.pck`，还需要外置 manifest：

```bash
STS2AIAgent.json
```

因此 `scripts/build-mod.sh` 必须把 manifest 一起复制到：

```bash
SlayTheSpire2.app/Contents/MacOS/mods/
```

只放 DLL/PCK 时，游戏不会把这个 Mod 当作完整本地 Mod 加载。

## 构建和安装

确认游戏数据目录：

```bash
export STS2_DATA_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"
```

单独构建 C# Mod：

```bash
dotnet build STS2AIAgent/STS2AIAgent.csproj -c Release
```

构建并安装到游戏目录：

```bash
./scripts/build-mod.sh \
  --configuration Release \
  --game-root "$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2"
```

## 启用游戏 Mod 加载

如果游戏日志出现类似信息：

```text
user has not yet seen the mods warning
```

说明游戏没有启用 Mod。可以在游戏 UI 里确认 Mod 提示，也可以修改设置文件。

本机设置文件示例：

```bash
~/Library/Application Support/SlayTheSpire2/steam/76561199527957431/settings.save
```

修改前先备份：

```bash
cp "$HOME/Library/Application Support/SlayTheSpire2/steam/76561199527957431/settings.save" \
   "$HOME/Library/Application Support/SlayTheSpire2/steam/76561199527957431/settings.save.bak-sts2-agent"
```

确保 JSON 中有：

```json
"mod_settings": {
  "mods_enabled": true,
  "mod_list": []
}
```

## 验证 Mod 加载

短启动并验证 `/health`：

```bash
./scripts/test-mod-load.sh \
  --game-root "$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2"
```

成功返回示例：

```json
{
  "service": "sts2-ai-agent",
  "mod_version": "0.8.0",
  "protocol_version": "2026-03-11-v1",
  "game_version": "v0.107.1",
  "status": "ready"
}
```

注意：这个脚本会短启动游戏并在验证结束后关闭它。如果正在手动操作游戏，不要把它和手动游戏窗口混在一起用。

## 验证 MCP/HTTP 读状态和动作

启动一局临时游戏会话：

```bash
./scripts/start-game-session.sh \
  --game-root "$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2"
```

读取状态：

```bash
curl -s http://127.0.0.1:8080/state
```

读取当前可执行动作：

```bash
curl -s http://127.0.0.1:8080/actions/available
```

执行动作前必须遵守硬边界：只调用 `available_actions` 里出现的动作。不要根据屏幕名猜动作。

本机验证中，游戏刚启动时会有几秒空窗：

- 初始可能是 `screen=UNKNOWN` 或 `screen=MAIN_MENU`
- `available_actions=[]`
- 等主菜单稳定后，出现 `open_character_select` 和 `open_timeline`

本机实测流程：

```bash
curl -s \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8080/action \
  -d '{"action":"open_character_select","client_context":{"source":"manual-run"}}'

curl -s \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8080/action \
  -d '{"action":"embark","client_context":{"source":"manual-run"}}'

curl -s \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8080/action \
  -d '{"action":"choose_event_option","option_index":0,"client_context":{"source":"manual-run"}}'

curl -s \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8080/action \
  -d '{"action":"choose_event_option","option_index":0,"client_context":{"source":"manual-run"}}'

curl -s \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8080/action \
  -d '{"action":"choose_map_node","option_index":0,"client_context":{"source":"manual-run"}}'
```

这条链路的实际结果：

- 主菜单 `screen=MAIN_MENU` 时，`available_actions` 包含 `open_character_select`
- 角色选择页 `screen=CHARACTER_SELECT` 时，默认选中 `IRONCLAD`，执行 `embark`
- Neow 事件选择第 0 项，获得稀有牌 `PRIMAL_FORCE` 和遗物 `ARCANE_SCROLL`
- 地图选择第 0 个普通怪节点，进入 `COMBAT`
- 敌人为 `SLUDGE_SPINNER`，初始生命 `41/41`
- 第二回合用 `PRIMAL_FORCE` 后连续打出 `GIANT_ROCK` 击杀敌人
- 战斗结束后 `screen=REWARD`，`available_actions` 包含 `resolve_rewards`、`collect_rewards_and_proceed`、`claim_reward`

战斗出牌的请求格式要注意：`play_card` 使用 `card_index`，有目标的牌还需要 `target_index`。

```bash
curl -s \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8080/action \
  -d '{"action":"play_card","card_index":0,"target_index":0,"client_context":{"source":"manual-run"}}'
```

`/actions/available` 里的动作描述有时只说 `play_card` 需要索引，但没有完整展开每张牌是否需要目标。写 agent 时应该以 `/state` 中每张手牌的字段为准，例如：

- `requires_target`
- `target_index_space`
- `valid_target_indices`

每次动作后还会短暂进入不可操作窗口，`available_actions` 可能只剩 `save_and_quit`。agent 不应该立刻判定卡住，应该轮询 `/actions/available`，或者使用 MCP 的 `wait_until_actionable` 等到动作窗口恢复。

## MCP 能力边界

目前可以规划给 agent 直接使用的接口：

- `health_check` / `/health`：确认 Mod 服务在线和游戏版本
- `get_game_state` / `/state`：读取结构化游戏状态
- `get_available_actions` / `/actions/available`：读取当前可执行动作边界
- `act` / `/action`：执行动作
- `wait_until_actionable`：等待进入可操作状态，避免启动和过场空窗
- 游戏知识查询接口：读取 cards、relics、potions、events、monsters 等静态数据

已经实测通过的部分：

- 从主菜单进入角色选择
- 用铁甲战士 `IRONCLAD` 开局
- 处理第一个 Neow 选项并进入地图
- 选择第一个普通怪节点
- 读取战斗手牌、敌人、意图、能量、生命
- 使用 `card_index` 和 `target_index` 打出攻击牌
- 使用 `card_index` 打出无需目标的防御牌
- 结束回合并继续第二回合
- 击杀第一只怪并进入奖励页

当前不应该宣称已经完全可靠的部分：

- 战斗中的所有卡牌、目标、药水、确认按钮路径
- 事件、商店、篝火、奖励、地图分支的全量覆盖
- 连胜统计、失败恢复、崩溃恢复
- Steam 云存档和已有 modded 存档的隔离策略

后续团队开发建议先把验证拆成阶段：

1. 主菜单：打开角色选择、选择角色、开始游戏
2. 地图：选择第一个可走节点
3. 战斗：读取手牌、敌人、意图，执行有目标和无目标的基础卡牌
4. 奖励：跳过或选择奖励
5. 一层闭环：完成若干房间
6. 失败恢复：崩溃、卡死、动作超时后重启并恢复

## 已保存的本地提交

当前本地已有两个基础提交：

```text
e96134d Initial STS2 agent project import
e722759 Adapt mod build for current STS2
```

第二个提交包含：

- 修复 `CanUseOrRemovePotions` 到 `CanRemovePotions`
- 修复 macOS Python 3.9 下 `scripts/lib-sts2.sh` 的类型语法
- 修复 `scripts/build-mod.sh`，安装 `STS2AIAgent.json`

## 已知注意事项

- 当前机器上还安装了其他 Workshop Mod：`ModConfig`、`DamageMeter`。做 agent 稳定性验证时，最好使用干净 Mod 环境。
- 日志里曾出现已有 modded 存档版本高于当前游戏可读版本的提示，这更像 Steam 云存档或其他 Mod 存档状态，不是 STS2AIAgent 编译修复本身导致。
- 游戏日志会反复出现一些本地化格式化错误，例如缺少 `Damage`、`Block`、`IfUpgraded` selector。它们目前不影响 `/state` 和 `/action` 的主链路，但后续可以单独清理，降低日志噪声。
- 本机实测开局时铁甲战士处于 Ascension 10。团队做评测时应该统一设置难度、种子和 Mod 列表。
- Codex 或测试脚本短启动游戏后关闭临时进程是正常行为；如果是你手动打开的游戏窗口，不要同时跑会自动关闭进程的验证脚本。
