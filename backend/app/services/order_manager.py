from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.brokers.base import BrokerInterface, BrokerOrder, OrderRequest
from app.core.event_bus import EventBus
from app.core.events import EventType
from app.core.market_state import MarketState
from app.db.base import SessionLocal
from app.db.models import Order

logger = logging.getLogger("orders")


class OrderManager:
    """Owns the order lifecycle: submission, cancellation, modification,
    partial fills, fill events. Entries arrive only via RISK_APPROVED
    (never directly from a strategy). Exits (stop/target are bracketed on
    the entry order; time-based/manual/emergency exits) are submitted
    directly via close_position, since flattening an existing position
    never increases risk and doesn't need re-validation."""

    def __init__(self, event_bus: EventBus, market_state: MarketState, broker: BrokerInterface) -> None:
        self._bus = event_bus
        self._state = market_state
        self._broker = broker
        # broker_order_id -> metadata needed to interpret fills
        self._order_meta: dict[str, dict[str, Any]] = {}

        self._bus.subscribe(EventType.RISK_APPROVED, self._on_risk_approved)

    async def _on_risk_approved(self, event) -> None:
        payload = event.payload
        strategy = payload["strategy"]
        symbol = payload["symbol"]
        direction = payload["direction"]
        quantity = float(payload["quantity"])
        side = "buy" if direction == "long" else "sell"

        request = OrderRequest(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type="market",
            stop_price=payload.get("stop_price"),
            take_profit_price=payload.get("take_profit_price"),
        )
        await self._submit(request, strategy=strategy, direction=direction, intent="entry", signal=payload)

    async def close_position(self, symbol: str, *, reason: str = "manual") -> BrokerOrder | None:
        position = self._state.active_positions.get(symbol)
        if position is None:
            return None
        direction = position["direction"]
        side = "sell" if direction == "long" else "buy"
        request = OrderRequest(symbol=symbol, side=side, quantity=abs(position["quantity"]), order_type="market")
        return await self._submit(
            request, strategy=position.get("strategy", "unknown"), direction=direction, intent="exit", signal={"reason": reason}
        )

    async def close_all(self, *, reason: str = "emergency") -> list[BrokerOrder]:
        results = []
        for symbol in list(self._state.active_positions.keys()):
            order = await self.close_position(symbol, reason=reason)
            if order:
                results.append(order)
        return results

    async def _submit(
        self, request: OrderRequest, *, strategy: str, direction: str, intent: str, signal: dict[str, Any]
    ) -> BrokerOrder:
        try:
            broker_order = await self._broker.place_order(request)
        except Exception as exc:
            logger.exception("order submission failed")
            await self._bus.publish(
                EventType.ORDER_REJECTED,
                source="order_manager",
                payload={"strategy": strategy, "symbol": request.symbol, "reason": str(exc)},
            )
            raise

        self._order_meta[broker_order.broker_order_id] = {
            "strategy": strategy,
            "direction": direction,
            "intent": intent,
            "signal": signal,
        }

        async with SessionLocal() as session:
            order_row = Order(
                broker_order_id=broker_order.broker_order_id,
                strategy=strategy,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                stop_price=request.stop_price,
                take_profit_price=request.take_profit_price,
                status="submitted",
                submitted_at=datetime.now(UTC),
            )
            session.add(order_row)
            await session.commit()

        self._state.upsert_order(
            broker_order.broker_order_id,
            {"strategy": strategy, "symbol": request.symbol, "side": request.side, "quantity": request.quantity, "status": "submitted"},
        )
        await self._bus.publish(
            EventType.ORDER_SUBMITTED,
            source="order_manager",
            payload={
                "broker_order_id": broker_order.broker_order_id,
                "strategy": strategy,
                "symbol": request.symbol,
                "side": request.side,
                "quantity": request.quantity,
                "intent": intent,
                "direction": direction,
            },
        )
        return broker_order

    async def cancel_order(self, broker_order_id: str) -> None:
        await self._broker.cancel_order(broker_order_id)
        self._state.remove_order(broker_order_id)
        async with SessionLocal() as session:
            row = (
                await session.execute(select(Order).where(Order.broker_order_id == broker_order_id))
            ).scalars().first()
            if row:
                row.status = "cancelled"
                row.cancelled_at = datetime.now(UTC)
                await session.commit()
        await self._bus.publish(
            EventType.ORDER_CANCELLED, source="order_manager", payload={"broker_order_id": broker_order_id}
        )

    async def cancel_all(self) -> None:
        for broker_order_id in list(self._state.active_orders.keys()):
            await self.cancel_order(broker_order_id)

    async def handle_fill(self, broker_order: BrokerOrder) -> None:
        """Invoked by the broker's fill stream (see engine wiring). Must be
        idempotent - duplicate fill notifications for the same order/status
        are safely ignored."""
        meta = self._order_meta.get(broker_order.broker_order_id, {})
        strategy = meta.get("strategy", "unknown")
        intent = meta.get("intent", "entry")
        direction = meta.get("direction", "long")

        async with SessionLocal() as session:
            row = (
                await session.execute(select(Order).where(Order.broker_order_id == broker_order.broker_order_id))
            ).scalars().first()
            if row is None:
                return
            if row.status == "filled" and broker_order.status == "filled":
                return  # idempotent: already processed

            row.filled_quantity = broker_order.filled_quantity
            row.avg_fill_price = broker_order.avg_fill_price
            row.status = broker_order.status
            if broker_order.status == "filled":
                row.filled_at = datetime.now(UTC)
            await session.commit()

        payload = {
            "broker_order_id": broker_order.broker_order_id,
            "strategy": strategy,
            "symbol": broker_order.symbol,
            "side": broker_order.side,
            "direction": direction,
            "intent": intent,
            "quantity": broker_order.quantity,
            "filled_quantity": broker_order.filled_quantity,
            "avg_fill_price": broker_order.avg_fill_price,
            "status": broker_order.status,
        }

        if broker_order.status == "filled":
            self._state.remove_order(broker_order.broker_order_id)
            await self._bus.publish(EventType.ORDER_FILLED, source="order_manager", payload=payload)
        elif broker_order.status in ("partially_filled", "partiallyfilled"):
            self._state.upsert_order(broker_order.broker_order_id, payload)
            await self._bus.publish(EventType.ORDER_PARTIALLY_FILLED, source="order_manager", payload=payload)
        elif broker_order.status in ("rejected",):
            self._state.remove_order(broker_order.broker_order_id)
            await self._bus.publish(EventType.ORDER_REJECTED, source="order_manager", payload=payload)
