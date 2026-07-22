from __future__ import annotations

import logging

from app.core.event_bus import EventBus
from app.core.events import EventType
from app.core.market_state import MarketState
from app.services.order_manager import OrderManager
from app.services.portfolio_manager import PortfolioManager
from app.services.position_manager import PositionManager
from app.services.strategy_manager import StrategyManager

logger = logging.getLogger("recovery")


class StateRecoveryService:
    """Rebuilds runtime trading state after a restart: reload positions and
    orders from the broker (source of truth), refresh the account
    snapshot, then let every strategy rebuild its own state (opening
    range, ATR/envelope, bias) before trading resumes."""

    def __init__(
        self,
        event_bus: EventBus,
        market_state: MarketState,
        position_manager: PositionManager,
        order_manager: OrderManager,
        portfolio_manager: PortfolioManager,
        strategy_manager: StrategyManager,
    ) -> None:
        self._bus = event_bus
        self._state = market_state
        self._positions = position_manager
        self._orders = order_manager
        self._portfolio = portfolio_manager
        self._strategies = strategy_manager

    async def recover(self) -> None:
        await self._bus.publish(EventType.RECOVERY_STARTED, source="state_recovery", payload={"component": "state"})
        try:
            await self._portfolio.refresh_account()
            await self._positions.reconcile()
            await self._reload_open_orders()
            await self._strategies.recover_all()
        except Exception:
            logger.exception("state recovery failed")
            await self._bus.publish(EventType.RECOVERY_FAILED, source="state_recovery", payload={"component": "state"})
            raise

        await self._bus.publish(EventType.STATE_RESTORED, source="state_recovery", payload={})
        await self._bus.publish(EventType.RECOVERY_COMPLETED, source="state_recovery", payload={"component": "state"})
        logger.info("state recovery complete")

    async def _reload_open_orders(self) -> None:
        try:
            open_orders = await self._orders._broker.get_open_orders()  # noqa: SLF001
        except Exception:
            logger.exception("failed to reload open orders during recovery")
            return
        for order in open_orders:
            self._state.upsert_order(
                order.broker_order_id,
                {
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": order.quantity,
                    "filled_quantity": order.filled_quantity,
                    "status": order.status,
                },
            )
