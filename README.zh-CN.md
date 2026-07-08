# SLS2 Game Agent

完整说明请看 [README.md](./README.md)。

本仓库基于上游开源 [CharTyr/STS2-Agent](https://github.com/CharTyr/STS2-Agent) 项目继续开发，目标是在《Slay the Spire 2》上构建专用游戏 agent。当前仓库包含：

- C# STS2 Mod：把游戏状态和操作暴露为本地 HTTP API；
- Python MCP server：把本地 API 包装为 MCP 工具；
- STS2 `v0.107.1` 的 macOS 本地适配记录；
- OpenSpec 团队协作规范；
- MVP0 的专用 agent runner 规划。

## 重要入口

- 安装、构建、OpenSpec、MVP0：[README.md](./README.md)
- 团队协作流程：[docs/team-workflow.md](./docs/team-workflow.md)
- 本地版本适配记录：[docs/macos-v0.107.1-local-adaptation.md](./docs/macos-v0.107.1-local-adaptation.md)
- OpenSpec 协作契约：[openspec/specs/agent-collaboration-contracts/spec.md](./openspec/specs/agent-collaboration-contracts/spec.md)
- MCP 工具说明：[mcp_server/README.md](./mcp_server/README.md)

## 归属说明

本项目不是从零原创项目。当前代码基础来自上游开源 [CharTyr/STS2-Agent](https://github.com/CharTyr/STS2-Agent)；本团队在此基础上做版本适配、团队协作规范和专用 agent runner 开发。

公开发布、派生文档和后续 fork 中都应保留上游归属说明，并继续保留现有 AGPL-3.0-only 许可证说明。
