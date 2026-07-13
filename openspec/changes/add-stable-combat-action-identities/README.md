# Add Stable Combat Action Identities

为 combat hand cards 和 enemies 提供进程内稳定 instance ID，使 Runtime 可以在一次 LLM
规划后逐步执行，而不依赖会因出牌、烧牌、弃牌、抽牌或死亡变化的 index。

相关长期契约：`openspec/specs/agent-collaboration-contracts/spec.md`。

