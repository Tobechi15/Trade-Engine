from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import text

from app.brokers.base import BrokerInterface
from app.core.event_bus import EventBus
from app.core.events import EventType
from app.db.base import SessionLocal
from app.services.market_data_service import MarketDataService
from app.services.order_manager import OrderManager

logger = logging.getLogger("recovery")

BACKOFF_SCHEDULE_SECONDS = [1, 2, 5, 10, 30]
# If a stream ran at least this long before dropping, treat it as having
# been genuinely connected (reset backoff to the fast end) rather than a
# repeated hard failure (e.g. bad credentials/URL) that should keep
# backing off - otherwise a connection that authenticates then drops
# immediately every time would spin at ~1s intervals forever and trip the
# provider's rate limit (this is exactly what was happening before this
# fix: Massive was getting hit roughly once a second).
STABLE_CONNECTION_SECONDS = 15.0


class RecoveryService:
    """Monitors infrastructure (broker, market data, database, scheduler)
    and reconnects with exponential backoff on failure. Rebuilding trading
    state itself is the State Recovery Service's job - this service only
    owns connectivity."""

    def __init__(
        self,
        event_bus: EventBus,
        broker: BrokerInterface,
        market_data_service: MarketDataService,
        order_manager: OrderManager,
    ) -> None:
        self._bus = event_bus
        self._broker = broker
        self._market_data = market_data_service
        self._order_manager = order_manager
        self._tasks: list[asyncio.Task] = []
        self._history: list[dict] = []

        self.broker_status = "disconnected"
        self.market_data_status = "disconnected"
        self.database_status = "unknown"
        self.scheduler_status = "unknown"
        self._reconnect_attempts: dict[str, int] = {"broker": 0, "market_data": 0}

    def start(self) -> None:
        self._tasks.append(asyncio.create_task(self._supervise_broker(), name="recovery-broker"))
        self._tasks.append(asyncio.create_task(self._supervise_market_data(), name="recovery-market-data"))
        self._tasks.append(asyncio.create_task(self._monitor_database(), name="recovery-database"))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    def _record(self, component: str, result: str, duration_seconds: float, failure_type: str = "recoverable") -> None:
        self._history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "component": component,
                "failure_type": failure_type,
                "recovery_duration_seconds": duration_seconds,
                "result": result,
            }
        )
        self._history = self._history[-200:]

    async def _supervise(self, component: str, run_stream: Callable[[], Awaitable[None]]) -> None:
        """Runs `run_stream()` in a loop. On failure, waits with growing
        backoff before retrying - the backoff only resets to the fast end
        once a connection has actually stayed up for a while, so a stream
        that authenticates then drops instantly every time still backs off
        properly instead of hammering the provider."""
        was_healthy = False
        while True:
            attempt = self._reconnect_attempts.get(component, 0)
            started_at = datetime.now(UTC)
            try:
                self._set_status(component, "healthy")
                was_healthy = True
                await run_stream()
                # A stream normally only returns by raising on disconnect;
                # a clean return is unusual but treat it as "reconnect now".
            except asyncio.CancelledError:
                raise
            except Exception:
                ran_for = (datetime.now(UTC) - started_at).total_seconds()
                self._set_status(component, "disconnected")
                logger.warning("%s stream failed after %.1fs", component, ran_for, exc_info=True)

                if was_healthy:
                    await self._bus.publish(
                        EventType.RECOVERY_STARTED, source="recovery", payload={"component": component}
                    )
                was_healthy = False

                if ran_for >= STABLE_CONNECTION_SECONDS:
                    attempt = 0

                delay = BACKOFF_SCHEDULE_SECONDS[min(attempt, len(BACKOFF_SCHEDULE_SECONDS) - 1)]
                self._reconnect_attempts[component] = attempt + 1
                self._record(component, "retrying", delay, failure_type="recoverable")
                await asyncio.sleep(delay)
                continue

            # Reached only on a clean (non-exception) return from run_stream.
            self._reconnect_attempts[component] = 0

    def _set_status(self, component: str, status: str) -> None:
        previous = self.broker_status if component == "broker" else self.market_data_status
        if component == "broker":
            self.broker_status = status
        else:
            self.market_data_status = status

        if status == "healthy" and previous != "healthy":
            event_type = EventType.BROKER_RECONNECTED if component == "broker" else EventType.MARKET_DATA_RECONNECTED
            asyncio.create_task(self._announce_recovered(component, event_type))

    async def _announce_recovered(self, component: str, event_type: EventType) -> None:
        await self._bus.publish(event_type, source="recovery", payload={"component": component})
        await self._bus.publish(EventType.RECOVERY_COMPLETED, source="recovery", payload={"component": component})
        self._record(component, "recovered", 0.0)

    async def _supervise_broker(self) -> None:
        await self._supervise("broker", lambda: self._broker.stream_fills(self._order_manager.handle_fill))

    async def _supervise_market_data(self) -> None:
        await self._supervise("market_data", self._market_data._run_stream)  # noqa: SLF001 - internal supervision

    async def _monitor_database(self) -> None:
        while True:
            try:
                async with SessionLocal() as session:
                    await session.execute(text("SELECT 1"))
                self.database_status = "healthy"
            except Exception:
                self.database_status = "disconnected"
                logger.warning("database health check failed", exc_info=True)
            await asyncio.sleep(30)

    def status(self) -> dict:
        return {
            "broker": self.broker_status,
            "market_data": self.market_data_status,
            "database": self.database_status,
            "scheduler": self.scheduler_status,
            "reconnect_attempts": self._reconnect_attempts,
        }

    def history(self, limit: int = 50) -> list[dict]:
        return self._history[-limit:]
