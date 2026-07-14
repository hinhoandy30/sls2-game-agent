from __future__ import annotations

from typing import Any

from .agent_context import RunContextStore
from .contracts import GameStateSnapshot
from .llm import OpenAICompatiblePolicy
from .policies import Policy, ScreenRouter
from .strategy import SpecialistAgentName, StrategyProvider


class RouteStrategyAgent(OpenAICompatiblePolicy):
    def __init__(self, context_store: RunContextStore, strategy_provider: StrategyProvider | None = None, **kwargs: Any) -> None:
        strategy_provider = strategy_provider or StrategyProvider()
        strategy = strategy_provider.get("route_strategy")
        super().__init__(
            **kwargs,
            agent_name="route_strategy",
            agent_instruction=strategy.render_instruction(),
            context_provider=lambda state: context_store.prompt_context(state, "route_strategy"),
            metadata_provider=_metadata_provider(context_store, strategy_provider, "route_strategy"),
            strategy_update_handler=context_store.apply_strategy_update,
        )


class CombatAgent(OpenAICompatiblePolicy):
    def __init__(self, context_store: RunContextStore, strategy_provider: StrategyProvider | None = None, **kwargs: Any) -> None:
        strategy_provider = strategy_provider or StrategyProvider()
        strategy = strategy_provider.get("combat")
        super().__init__(
            **kwargs,
            agent_name="combat",
            agent_instruction=strategy.render_instruction(),
            context_provider=lambda state: context_store.prompt_context(state, "combat"),
            metadata_provider=_metadata_provider(context_store, strategy_provider, "combat"),
        )


class RunDevelopmentAgent(OpenAICompatiblePolicy):
    def __init__(self, context_store: RunContextStore, strategy_provider: StrategyProvider | None = None, **kwargs: Any) -> None:
        strategy_provider = strategy_provider or StrategyProvider()
        strategy = strategy_provider.get("run_development")
        super().__init__(
            **kwargs,
            agent_name="run_development",
            agent_instruction=strategy.render_instruction(),
            context_provider=lambda state: context_store.prompt_context(state, "run_development"),
            metadata_provider=_metadata_provider(context_store, strategy_provider, "run_development"),
            strategy_update_handler=context_store.apply_strategy_update,
        )


class AgentOrchestrator(ScreenRouter):
    """Deterministic specialist router. Runtime still owns validation and live I/O."""

    DEVELOPMENT_SCREENS = {"REWARD", "CARD_SELECTION", "BUNDLE_SELECTION", "EVENT", "SHOP", "REST", "CHEST"}

    def __init__(
        self,
        *,
        context_store: RunContextStore,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        enable_action_plan: bool = True,
        max_plan_actions: int = 5,
        max_retries: int = 2,
        request_timeout_seconds: float = 60.0,
        strategy_provider: StrategyProvider | None = None,
    ) -> None:
        super().__init__()
        self.context_store = context_store
        self.strategy_provider = strategy_provider or StrategyProvider()
        common = {
            "model": model,
            "api_base": api_base,
            "api_key": api_key,
            "enable_action_plan": enable_action_plan,
            "max_plan_actions": max_plan_actions,
            "max_retries": max_retries,
            "request_timeout_seconds": request_timeout_seconds,
        }
        self.route_agent = RouteStrategyAgent(context_store, self.strategy_provider, **common)
        self.combat_agent = CombatAgent(context_store, self.strategy_provider, **common)
        self.development_agent = RunDevelopmentAgent(context_store, self.strategy_provider, **common)

    def select(self, state: GameStateSnapshot) -> Policy:
        self.context_store.observe(state)
        if state.screen == "MAP":
            return self.route_agent
        if state.screen == "COMBAT":
            return self.combat_agent
        if state.screen in self.DEVELOPMENT_SCREENS:
            return self.development_agent
        return super().select(state)


def _metadata_provider(
    context_store: RunContextStore,
    strategy_provider: StrategyProvider,
    agent_name: SpecialistAgentName,
) -> Any:
    def provide(state: GameStateSnapshot) -> dict[str, Any]:
        return {
            **context_store.decision_metadata(state, agent_name),
            "strategy": strategy_provider.get(agent_name).metadata(),
        }

    return provide
