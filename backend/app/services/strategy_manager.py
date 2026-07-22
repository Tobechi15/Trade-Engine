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
            await strategy.initialize()

    async def start_all(self) -> None:
        for strategy in self._strategies.values():
            if strategy.enabled:
                await strategy.start()

    async def stop_all(self) -> None:
        for strategy in self._strategies.values():
            await strategy.stop()

    async def recover_all(self) -> None:
        for strategy in self._strategies.values():
            if strategy.enabled:
                await strategy.recover_state()

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
