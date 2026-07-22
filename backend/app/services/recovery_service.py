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

    async def _backoff_reconnect(self, component: str, reconnect: Callable[[], Awaitable[None]]) -> bool:
        attempt = self._reconnect_attempts.get(component, 0)
        start = datetime.now(UTC)
        await self._bus.publish(EventType.RECOVERY_STARTED, source="recovery", payload={"component": component})
        delay = BACKOFF_SCHEDULE_SECONDS[min(attempt, len(BACKOFF_SCHEDULE_SECONDS) - 1)]
        await asyncio.sleep(delay)
        self._reconnect_attempts[component] = attempt + 1
        try:
            await reconnect()
        except Exception:
            logger.warning("reconnect attempt failed for %s", component, exc_info=True)
            duration = (datetime.now(UTC) - start).total_seconds()
            self._record(component, "failed", duration)
            await self._bus.publish(EventType.RECOVERY_FAILED, source="recovery", payload={"component": component})
            return False

        self._reconnect_attempts[component] = 0
        duration = (datetime.now(UTC) - start).total_seconds()
        self._record(component, "recovered", duration)
        event_type = EventType.BROKER_RECONNECTED if component == "broker" else EventType.MARKET_DATA_RECONNECTED
        await self._bus.publish(event_type, source="recovery", payload={"component": component})
        await self._bus.publish(EventType.RECOVERY_COMPLETED, source="recovery", payload={"component": component})
        return True

    async def _supervise_broker(self) -> None:
        while True:
            try:
                self.broker_status = "healthy"
                await self._broker.stream_fills(self._order_manager.handle_fill)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.broker_status = "disconnected"
                logger.warning("broker stream disconnected", exc_info=True)
                recovered = False
                while not recovered:
                    recovered = await self._backoff_reconnect("broker", self._broker.connect)
                self.broker_status = "healthy"

    async def _supervise_market_data(self) -> None:
        while True:
            try:
                self.market_data_status = "healthy"
                await self._market_data._run_stream()  # noqa: SLF001 - internal supervision
            except asyncio.CancelledError:
                raise
            except Exception:
                self.market_data_status = "disconnected"
                logger.warning("market data stream disconnected", exc_info=True)
                recovered = False
                while not recovered:
                    recovered = await self._backoff_reconnect("market_data", self._market_data.connect)
                self.market_data_status = "healthy"

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
