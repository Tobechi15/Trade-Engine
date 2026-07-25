from __future__ import annotations

import logging

from app.strategies.base import Strategy

logger = logging.getLogger("strategy")


class StrategyManager:
    """Loads, starts, stops and recovers every strategy. Each strategy
    subscribes to the events it needs directly against the Event Bus; this
    manager is the dashboard/API-facing control surface for lifecycle
    operations (enable/disable/reload/status)."""

    def __init__(self, strategies: dict[str, Strategy]) -> None:
        self._strategies = strategies

    def get(self, name: str) -> Strategy | None:
        return self._strategies.get(name)

    def all(self) -> list[Strategy]:
        return list(self._strategies.values())

    async def initialize_all(self) -> None:
        for strategy in self._strategies.values():
            await self._guarded(strategy.name, "initialize", strategy.initialize())

    async def start_all(self) -> None:
        for strategy in self._strategies.values():
            if strategy.enabled:
                await self._guarded(strategy.name, "start", strategy.start())

    async def stop_all(self) -> None:
        for strategy in self._strategies.values():
            await self._guarded(strategy.name, "stop", strategy.stop())

    async def recover_all(self) -> None:
        for strategy in self._strategies.values():
            if strategy.enabled:
                await self._guarded(strategy.name, "recover_state", strategy.recover_state())

    async def _guarded(self, strategy_name: str, phase: str, coro) -> None:
        # One strategy's data hiccup (e.g. a market-data call failing
        # during recover_state) must never crash engine startup for every
        # other strategy - log it, disable that strategy, and move on.
        try:
            await coro
        except Exception:
            logger.exception("strategy '%s' failed during %s - disabling it", strategy_name, phase)
            self.disable(strategy_name)

    def enable(self, name: str) -> None:
        if name in self._strategies:
            self._strategies[name].enabled = True

    def disable(self, name: str) -> None:
        if name in self._strategies:
            self._strategies[name].enabled = False

    async def reload(self, name: str) -> None:
        strategy = self._strategies.get(name)
        if strategy is None:
            return
        await strategy.stop()
        await strategy.initialize()
        await strategy.start()

    def status(self) -> list[dict]:
        return [
            {
                "name": strategy.name,
                "enabled": strategy.enabled,
                "config": strategy.config,
            }
            for strategy in self._strategies.values()
        ]
