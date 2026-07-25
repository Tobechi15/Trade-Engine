from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.brokers.base import BrokerInterface
from app.core.event_bus import EventBus
from app.core.events import EventType
from app.core.market_state import MarketState

logger = logging.getLogger("system")


class PositionManager:
    """Maintains active positions and their state. Reconciles against the
    broker every minute; the broker is always the source of truth - local
    state is corrected to match it, never the other way around."""

    def __init__(self, event_bus: EventBus, market_state: MarketState, broker: BrokerInterface) -> None:
        self._bus = event_bus
        self._state = market_state
        self._broker = broker

        self._bus.subscribe(EventType.ORDER_FILLED, self._on_order_filled)
        self._bus.subscribe(EventType.NEW_QUOTE, self._on_new_quote)

    async def _on_new_quote(self, event) -> None:
        payload = event.payload
        self.update_mark_price(payload["symbol"], payload["price"])

    async def _on_order_filled(self, event) -> None:
        payload = event.payload
        symbol = payload["symbol"]
        intent = payload.get("intent", "entry")
        direction = payload.get("direction", "long")
        quantity = float(payload.get("filled_quantity") or payload.get("quantity", 0))
        price = payload.get("avg_fill_price")

        if intent == "entry":
            existing = self._state.active_positions.get(symbol)
            if existing:
                total_qty = existing["quantity"] + quantity
                existing["entry_price"] = (
                    (existing["entry_price"] * existing["quantity"] + (price or existing["entry_price"]) * quantity)
                    / total_qty
                    if total_qty
                    else existing["entry_price"]
                )
                existing["quantity"] = total_qty
                self._state.upsert_position(symbol, existing)
                await self._bus.publish(EventType.POSITION_UPDATED, source="position_manager", payload=existing)
            else:
                position = {
                    "symbol": symbol,
                    "strategy": payload["strategy"],
                    "direction": direction,
                    "quantity": quantity,
                    "entry_price": price,
                    "current_price": price,
                    "opened_at": datetime.now(UTC).isoformat(),
                }
                self._state.upsert_position(symbol, position)
                await self._bus.publish(EventType.POSITION_OPENED, source="position_manager", payload=position)
        elif intent == "partial_exit":
            position = self._state.active_positions.get(symbol)
            if position is None:
                return
            position["quantity"] = max(0.0, position["quantity"] - quantity)
            self._state.upsert_position(symbol, position)
            await self._bus.publish(
                EventType.POSITION_UPDATED,
                source="position_manager",
                payload={**position, "partial_exit_price": price, "partial_exit_quantity": quantity},
            )
        else:  # full exit
            position = self._state.active_positions.get(symbol)
            if position is None:
                return
            self._state.remove_position(symbol)
            closed = {**position, "exit_price": price, "closed_at": datetime.now(UTC).isoformat()}
            await self._bus.publish(EventType.POSITION_CLOSED, source="position_manager", payload=closed)

    def update_mark_price(self, symbol: str, price: float) -> None:
        position = self._state.active_positions.get(symbol)
        if position is None:
            return
        position["current_price"] = price

    async def reconcile(self) -> None:
        """Broker is source of truth: pull live positions and correct local
        state to match. Runs on a scheduled interval (every minute)."""
        try:
            broker_positions = {p.symbol: p for p in await self._broker.get_positions()}
        except Exception:
            logger.exception("position reconciliation failed to reach broker")
            return

        local_symbols = set(self._state.active_positions.keys())
        broker_symbols = set(broker_positions.keys())

        for symbol in local_symbols - broker_symbols:
            position = self._state.active_positions.get(symbol)
            self._state.remove_position(symbol)
            if position:
                await self._bus.publish(
                    EventType.POSITION_CLOSED,
                    source="position_manager",
                    payload={**position, "closed_at": datetime.now(UTC).isoformat(), "reason": "broker_reconciliation"},
                )

        for symbol in broker_symbols:
            broker_pos = broker_positions[symbol]
            local_pos = self._state.active_positions.get(symbol)
            if local_pos is None:
                position = {
                    "symbol": symbol,
                    "strategy": "unknown",
                    "direction": broker_pos.side,
                    "quantity": broker_pos.quantity,
                    "entry_price": broker_pos.avg_entry_price,
                    "current_price": broker_pos.avg_entry_price,
                    "opened_at": datetime.now(UTC).isoformat(),
                }
                self._state.upsert_position(symbol, position)
                await self._bus.publish(EventType.POSITION_OPENED, source="position_manager", payload=position)
            elif abs(local_pos["quantity"] - broker_pos.quantity) > 1e-9:
                local_pos["quantity"] = broker_pos.quantity
                local_pos["entry_price"] = broker_pos.avg_entry_price
                self._state.upsert_position(symbol, local_pos)
                await self._bus.publish(EventType.POSITION_UPDATED, source="position_manager", payload=local_pos)
