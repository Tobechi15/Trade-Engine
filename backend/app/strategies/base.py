from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.event_bus import Event, EventBus
from app.core.events import EventType
from app.core.market_calendar import MarketCalendarService
from app.core.market_state import MarketState
from app.core.time_service import TimeService
from app.services.order_manager import OrderManager


class Strategy(ABC):
    """Every strategy implements this interface and shares the same
    execution, risk, recovery and analytics infrastructure. A strategy
    never places orders directly, never talks to a broker or market data
    provider, never stores market history, and never calculates risk
    itself - it only publishes signals through the Event Bus."""

    name: str

    def __init__(
        self,
        event_bus: EventBus,
        market_state: MarketState,
        market_calendar: MarketCalendarService,
        order_manager: OrderManager,
        config: dict[str, Any],
    ) -> None:
        self._bus = event_bus
        self._state = market_state
        self._calendar = market_calendar
        self._order_manager = order_manager
        self.config = config
        self.enabled = bool(config.get("enabled", True))
        # symbol -> in-flight trade context, used to assemble TRADE_ENTERED /
        # TRADE_EXITED performance-logging payloads.
        self._open_trades: dict[str, dict[str, Any]] = {}

        self._bus.subscribe_many(self.subscribed_events(), self._dispatch)
        self._bus.subscribe(EventType.ORDER_FILLED, self._on_order_filled)
        self._bus.subscribe(EventType.POSITION_CLOSED, self._on_position_closed)

    @abstractmethod
    def subscribed_events(self) -> list[EventType]: ...

    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def on_event(self, event: Event) -> None: ...

    @abstractmethod
    async def recover_state(self) -> None: ...

    async def _dispatch(self, event: Event) -> None:
        if not self.enabled:
            return
        await self.on_event(event)

    async def publish_signal(
        self,
        *,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_price: float,
        take_profit_price: float | None = None,
        allow_duplicate: bool = False,
    ) -> None:
        self._open_trades[symbol] = {
            "signal_time": TimeService.now_utc(),
            "direction": direction,
            "stop_price": stop_price,
            "take_profit_price": take_profit_price,
        }
        await self._bus.publish(
            EventType.SIGNAL_GENERATED,
            source=self.name,
            payload={
                "strategy": self.name,
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "take_profit_price": take_profit_price,
                "allow_duplicate": allow_duplicate,
            },
        )

    async def close_position(self, symbol: str, *, reason: str) -> None:
        await self._order_manager.close_position(symbol, reason=reason)

    async def partial_close_position(self, symbol: str, *, fraction: float, reason: str) -> None:
        """Closes part of the position (e.g. a partial take-profit) while
        keeping the trade context open - the eventual full close still
        finalizes TRADE_EXITED, with this leg's PnL folded in."""
        await self._order_manager.close_position(symbol, reason=reason, fraction=fraction)

    async def _on_order_filled(self, event: Event) -> None:
        payload = event.payload
        if payload.get("strategy") != self.name:
            return
        intent = payload.get("intent")
        symbol = payload["symbol"]
        ctx = self._open_trades.get(symbol)
        if ctx is None:
            return

        if intent == "partial_exit":
            if "entry_price" not in ctx:
                return
            exit_price = payload.get("avg_fill_price")
            filled_qty = payload.get("filled_quantity") or 0
            if exit_price is None or not filled_qty:
                return
            sign = 1 if ctx["direction"] == "long" else -1
            ctx["realized_pnl"] = ctx.get("realized_pnl", 0.0) + sign * (exit_price - ctx["entry_price"]) * filled_qty
            ctx["quantity"] = max(0.0, (ctx.get("quantity") or 0) - filled_qty)
            return

        if intent != "entry" or "entry_time" in ctx:
            return  # unknown intent, or already processed (idempotency)
        ctx["entry_time"] = TimeService.now_utc()
        ctx["entry_price"] = payload.get("avg_fill_price")
        ctx["quantity"] = payload.get("filled_quantity")
        ctx["original_quantity"] = ctx["quantity"]
        await self._bus.publish(
            EventType.TRADE_ENTERED,
            source=self.name,
            payload={
                "strategy": self.name,
                "symbol": payload["symbol"],
                "direction": ctx["direction"],
                "signal_time": ctx["signal_time"].isoformat(),
                "entry_time": ctx["entry_time"].isoformat(),
                "entry_price": ctx["entry_price"],
                "stop_price": ctx["stop_price"],
                "take_profit_price": ctx["take_profit_price"],
                "quantity": ctx["quantity"],
            },
        )

    async def _on_position_closed(self, event: Event) -> None:
        payload = event.payload
        if payload.get("strategy") != self.name:
            return
        symbol = payload["symbol"]
        ctx = self._open_trades.pop(symbol, None)
        if ctx is None or "entry_price" not in ctx:
            return
        entry_price = ctx.get("entry_price")
        exit_price = payload.get("exit_price") or entry_price
        remaining_quantity = ctx.get("quantity") or 0
        original_quantity = ctx.get("original_quantity", remaining_quantity)
        direction = ctx.get("direction")
        sign = 1 if direction == "long" else -1
        final_leg_pnl = sign * (exit_price - entry_price) * remaining_quantity if entry_price and exit_price else 0.0
        pnl = ctx.get("realized_pnl", 0.0) + final_leg_pnl
        risk_amount = (
            abs(entry_price - ctx["stop_price"]) * original_quantity if entry_price and ctx.get("stop_price") else None
        )
        r_multiple = pnl / risk_amount if pnl is not None and risk_amount else None
        entry_time = ctx.get("entry_time")
        exit_time = TimeService.now_utc()
        duration = (exit_time - entry_time).total_seconds() if entry_time else None

        await self._bus.publish(
            EventType.TRADE_EXITED,
            source=self.name,
            payload={
                "strategy": self.name,
                "symbol": symbol,
                "direction": direction,
                "signal_time": ctx["signal_time"].isoformat(),
                "entry_time": entry_time.isoformat() if entry_time else None,
                "exit_time": exit_time.isoformat(),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": original_quantity,
                "risk_amount": risk_amount,
                "pnl": pnl,
                "r_multiple": r_multiple,
                "duration_seconds": duration,
                "exit_reason": payload.get("reason", "signal"),
            },
        )
