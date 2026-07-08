# Design: Combat Policy V0

## Scope

CombatPolicyV0 should prioritize legality and simple tactical sanity:

1. If lethal is available, take lethal.
2. If incoming damage is dangerous, prefer block or defensive value.
3. Spend energy on playable high-value cards.
4. Re-read state after each action through Runtime.
5. End turn only when no useful legal play remains.

## Inputs

```python
decide(state: GameStateSnapshot, knowledge: KnowledgeContext, memory: RunMemory)
```

## Outputs

`PolicyDecision` with one `AgentAction`, `wait`, `stop`, or `needs_human`.

## Non-goals

- No deep search in MVP0.
- No card reward strategy.
- No long-term deck planning.
- No direct game API calls.

