from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.brokers.bybit_tradfi import BybitTradFiBroker
from app.config import Settings
from app.core.event_bus import EventBus
from app.core.events import EventType
from app.core.market_calendar import MarketCalendarService, market_calendar
from app.core.market_state import MarketState
from app.core.time_service import EXCHANGE_TZ, TimeService
from app.market_data.massive import MassiveMarketData
from app.services.analytics_service import AnalyticsService
from app.services.logging_service import LoggingService, configure_logging
from app.services.market_data_service import MarketDataService
from app.services.notification_service import NotificationService
from app.services.order_manager import OrderManager
from app.services.portfolio_manager import PortfolioManager
from app.services.position_manager import PositionManager
from app.services.recovery_service import RecoveryService
from app.services.risk_engine import RiskEngine
from app.services.state_recovery_service import StateRecoveryService
from app.services.strategy_manager import StrategyManager
from app.strategies.bias import FirstHourLastHour
from app.strategies.breadth_pullback import BreadthVwapPullback
from app.strategies.gap_fill import OpeningGapFill
from app.strategies.noise import NoiseBoundaryBreakout
from app.strategies.orb import OpeningRangeBreakout
from app.strategies.vwap_reversion import VwapMeanReversion

logger = logging.getLogger("system")

STRATEGY_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "strategies.yaml"


class EngineStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    RECOVERING = "recovering"


class TradingEngine:
    """Wires every core service together and owns the startup/shutdown
    sequence described in RECOVERY.md."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.status = EngineStatus.STOPPED
        self.started_at = None
        self.version = "0.1.0"

        self.event_bus = EventBus()
        self.market_state = MarketState()
        self.market_calendar: MarketCalendarService = market_calendar

        self.broker = BybitTradFiBroker(settings)
        self.market_data_provider = MassiveMarketData(settings)
        self.market_data_service = MarketDataService(self.event_bus, self.market_state, self.market_data_provider)

        self.order_manager = OrderManager(self.event_bus, self.market_state, self.broker)
        self.risk_engine = RiskEngine(self.event_bus, self.market_state)
        self.position_manager = PositionManager(self.event_bus, self.market_state, self.broker)
        self.portfolio_manager = PortfolioManager(self.event_bus, self.market_state, self.broker)
        self.notification_service = NotificationService(self.event_bus)
        self.logging_service = LoggingService(self.event_bus)
        self.analytics_service = AnalyticsService(self.event_bus)

        strategy_config = self._load_strategy_config()
        strategies = {
            "orb": OpeningRangeBreakout(
                self.event_bus, self.market_state, self.market_calendar, self.order_manager,
                strategy_config.get("orb", {}), market_data_service=self.market_data_service,
            ),
            "noise": NoiseBoundaryBreakout(
                self.event_bus, self.market_state, self.market_calendar, self.order_manager,
                strategy_config.get("noise", {}), market_data_service=self.market_data_service,
            ),
            "bias": FirstHourLastHour(
                self.event_bus, self.market_state, self.market_calendar, self.order_manager,
                strategy_config.get("bias", {}),
            ),
            "vwap_reversion": VwapMeanReversion(
                self.event_bus, self.market_state, self.market_calendar, self.order_manager,
                strategy_config.get("vwap_reversion", {}), market_data_service=self.market_data_service,
            ),
            "gap_fill": OpeningGapFill(
                self.event_bus, self.market_state, self.market_calendar, self.order_manager,
                strategy_config.get("gap_fill", {}), market_data_service=self.market_data_service,
            ),
            "breadth_pullback": BreadthVwapPullback(
                self.event_bus, self.market_state, self.market_calendar, self.order_manager,
                strategy_config.get("breadth_pullback", {}), market_data_service=self.market_data_service,
            ),
        }
        self.strategy_manager = StrategyManager(strategies)
        self._orb_strategy: OpeningRangeBreakout = strategies["orb"]  # type: ignore[assignment]

        self.recovery_service = RecoveryService(self.event_bus, self.broker, self.market_data_service, self.order_manager)
        self.state_recovery_service = StateRecoveryService(
            self.event_bus, self.market_state, self.position_manager, self.order_manager,
            self.portfolio_manager, self.strategy_manager,
        )

        self.scheduler = AsyncIOScheduler(timezone=EXCHANGE_TZ)

    def _load_strategy_config(self) -> dict:
        if STRATEGY_CONFIG_PATH.exists():
            return yaml.safe_load(STRATEGY_CONFIG_PATH.read_text()) or {}
        return {}

    async def start(self) -> None:
        configure_logging(self.settings.log_level)
        logger.info("engine starting")
        self.status = EngineStatus.STARTING

        await self.event_bus.start()
        await self.risk_engine.load_settings()

        # Broker/market-data connectivity is intentionally non-fatal here:
        # a missing/bad API key (or a provider outage) should degrade the
        # engine, not prevent it from starting at all. RecoveryService
        # (started below) retries both forever with backoff, and
        # /api/v1/health reports the real per-component status - see
        # RECOVERY.md's "trading stays paused until synchronized", not
        # "the whole engine refuses to boot".
        try:
            await self.broker.connect()
        except Exception:
            logger.exception("broker connection failed at startup - will keep retrying in the background")

        try:
            await self.market_data_service.connect()
        except Exception:
            logger.exception("market data connection failed at startup - will keep retrying in the background")

        try:
            self.market_state.tradeable_symbols = await self.broker.get_tradeable_symbols()
        except Exception:
            logger.exception("failed to fetch tradeable symbols from broker - universe filtering disabled")

        self._setup_scheduler()
        self.scheduler.start()

        await self.strategy_manager.initialize_all()

        self.status = EngineStatus.RECOVERING
        try:
            await self.state_recovery_service.recover()
        except Exception:
            # StateRecoveryService already logs + publishes RECOVERY_FAILED
            # internally; the safety net here just prevents an unexpected
            # failure from taking the whole engine down to "stopped" -
            # trading stays effectively paused (per-strategy failures
            # already disable themselves in StrategyManager), but the API,
            # dashboard, and health reporting keep working.
            logger.exception("state recovery failed - continuing with degraded/partial state")

        await self.strategy_manager.start_all()
        self.recovery_service.start()

        self.status = EngineStatus.RUNNING
        self.started_at = TimeService.now_utc()
        await self.event_bus.publish(EventType.ENGINE_STARTED, source="engine", payload={"version": self.version})
        logger.info("engine started")

    async def pause(self) -> None:
        self.risk_engine.pause_trading()
        self.status = EngineStatus.PAUSED
        await self.event_bus.publish(EventType.ENGINE_PAUSED, source="engine", payload={})

    async def resume(self) -> None:
        self.risk_engine.resume_trading()
        self.status = EngineStatus.RUNNING
        await self.event_bus.publish(EventType.ENGINE_RESUMED, source="engine", payload={})

    async def stop(self) -> None:
        logger.info("engine stopping")
        self.risk_engine.pause_trading()
        self.scheduler.shutdown(wait=False)
        await self.recovery_service.stop()
        await self.order_manager.cancel_all()
        await self.strategy_manager.stop_all()
        await self.market_data_service.disconnect()
        await self.broker.disconnect()
        await self.event_bus.publish(EventType.ENGINE_STOPPED, source="engine", payload={})
        await self.event_bus.stop()
        self.status = EngineStatus.STOPPED
        logger.info("engine stopped")

    def _setup_scheduler(self) -> None:
        def guarded(coro_factory):
            async def _run():
                if not self.market_calendar.is_market_day():
                    return
                await coro_factory()

            return _run

        self.scheduler.add_job(
            guarded(lambda: self._orb_strategy.build_universe()),
            CronTrigger(day_of_week="mon-fri", hour=8, minute=0, timezone=EXCHANGE_TZ),
            id="orb_universe_prep",
        )
        self.scheduler.add_job(
            guarded(lambda: self.event_bus.publish(EventType.MARKET_OPEN, source="scheduler", payload={})),
            CronTrigger(day_of_week="mon-fri", hour=9, minute=30, timezone=EXCHANGE_TZ),
            id="market_open",
        )
        self.scheduler.add_job(
            guarded(lambda: self.event_bus.publish(EventType.CLOSING_BIAS_START, source="scheduler", payload={})),
            CronTrigger(day_of_week="mon-fri", hour=15, minute=30, timezone=EXCHANGE_TZ),
            id="closing_bias_start",
        )

        async def regular_close():
            if not self.market_calendar.is_half_day():
                await self.event_bus.publish(EventType.MARKET_CLOSE, source="scheduler", payload={})

        async def half_day_close():
            if self.market_calendar.is_half_day():
                await self.event_bus.publish(EventType.MARKET_CLOSE, source="scheduler", payload={})

        self.scheduler.add_job(
            guarded(lambda: regular_close()), CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone=EXCHANGE_TZ), id="market_close"
        )
        self.scheduler.add_job(
            guarded(lambda: half_day_close()), CronTrigger(day_of_week="mon-fri", hour=13, minute=0, timezone=EXCHANGE_TZ), id="market_close_half_day"
        )

        async def reconcile_job():
            if self.market_calendar.is_open():
                await self.position_manager.reconcile()
                await self.portfolio_manager.refresh_account()

        self.scheduler.add_job(reconcile_job, "interval", seconds=60, id="position_reconciliation")

    def status_payload(self) -> dict:
        uptime = (TimeService.now_utc() - self.started_at).total_seconds() if self.started_at else 0
        return {
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": uptime,
            "broker": "connected" if self.broker.is_connected else "disconnected",
            "market_data": "connected" if self.market_data_provider.is_connected else "disconnected",
            "scheduler": "running" if self.scheduler.running else "stopped",
        }
