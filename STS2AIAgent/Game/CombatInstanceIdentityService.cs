using System.Runtime.CompilerServices;
using System.Threading;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Models;

namespace STS2AIAgent.Game;

/// <summary>
/// Assigns process-local identities to live combat objects.
/// These IDs survive index changes but do not survive a game restart.
/// </summary>
internal static class CombatInstanceIdentityService
{
    private static readonly ConditionalWeakTable<CardModel, Identity> CardIds = new();
    private static readonly ConditionalWeakTable<Creature, Identity> EnemyIds = new();
    private static long _nextCardId;
    private static long _nextEnemyId;

    public static string GetCardInstanceId(CardModel card)
    {
        return CardIds.GetValue(
            card,
            _ => new Identity($"card_{Interlocked.Increment(ref _nextCardId)}")).Value;
    }

    public static string GetEnemyInstanceId(Creature enemy)
    {
        return EnemyIds.GetValue(
            enemy,
            _ => new Identity($"enemy_{Interlocked.Increment(ref _nextEnemyId)}")).Value;
    }

    private sealed record Identity(string Value);
}
