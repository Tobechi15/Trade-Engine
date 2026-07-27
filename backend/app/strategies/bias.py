from __future__ import annotations

import logging

from app.core.event_bus import Event
from app.core.events import EventType
from app.core.time_service import TimeService
from app.strategies.base import Strategy

logger = logging.getLogger("strategy")


class FirstHourLastHour(Strategy):
    """Phase 1 (09:30-10:30): determine daily bias from first-hour price
    action. Phase 2: wait, no trading. Phase 3 (entry_time, default
    15:30): enter long/short per the morning bias. Phase 4 (exit_time,
    default 16:00 / MARKET_CLOSE): flatten - no overnight exposure."""

    name = "bias"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._universe: list[str] = self.config.get("universe", ["SPY", "QQQ"])
        self._bias_window_minutes: int = self.config.get("bias_window_minutes", 60)
        self._stop_pct: float = self.config.get("stop_pct", 0.5)
        self._neutral_threshold_pct: float = self.config.get("neutral_threshold_pct", 0.1)
        self._max_trades: int = self.config.get("maximum_trades", 2)
        self._trades_today = 0
        self._window_open: dict[str, float] = {}
        self._window_last_close: dict[str, float] = {}
        self._bias_locked_in = False

    def subscribed_events(self) -> list[EventType]:
        return [EventType.NEW_CANDLE, EventType.MARKET_OPEN, EventType.CLOSING_BIAS_START, EventType.MARKET_CLOSE]

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def on_event(self, event: Event) -> None:
        if event.event_type == EventType.MARKET_OPEN:
            self._trades_today = 0
            self._window_open.clear()
            self._window_last_close.clear()
            self._bias_locked_in = False
        elif event.event_type == EventType.NEW_CANDLE:
            await self._track_bias_window(event.payload)
        elif event.event_type == EventType.CLOSING_BIAS_START:
            await self._enter_positions()
        elif event.event_type == EventType.MARKET_CLOSE:
            for symbol, position in list(self._state.active_positions.items()):
                if position.get("strategy") == self.name:
                    await self.close_position(symbol, reason="scheduled_exit")

    async def _track_bias_window(self, payload: dict) -> None:
        symbol = payload["symbol"]
        if symbol not in self._universe:
            return
        exchange_time = TimeService.to_exchange(_parse_ts(payload["timestamp"]))
        open_time = exchange_time.replace(hour=9, minute=30, second=0, microsecond=0)
        window_end = open_time.replace(minute=(30 + self._bias_window_minutes) % 60, hour=open_time.hour + (30 + self._bias_window_minutes) // 60)
        if exchange_time > window_end:
            return
        self._window_open.setdefault(symbol, payload["open"])
        self._window_last_close[symbol] = payload["close"]
        self._compute_bias(symbol)

    def _compute_bias(self, symbol: str) -> None:
        open_price = self._window_open.get(symbol)
        last_close = self._window_last_close.get(symbol)
        if open_price is None or last_close is None or open_price == 0:
            return
        change_pct = (last_close - open_price) / open_price * 100
        if change_pct > self._neutral_threshold_pct:
            bias = "bullish"
        elif change_pct < -self._neutral_threshold_pct:
            bias = "bearish"
        else:
            bias = "neutral"
        self._state.daily_bias[symbol] = bias

    async def _enter_positions(self) -> None:
        if self._bias_locked_in:
            return
        self._bias_locked_in = True
        for symbol in self._universe:
            bias = self._state.daily_bias.get(symbol, "neutral")
            if bias == "neutral":
                continue
            quote = self._state.live_quotes.get(symbol)
            if quote is None:
                continue
            direction = "long" if bias == "bullish" else "short"

            if self._trades_today >= self._max_trades:
                await self.reject_signal(symbol=symbol, direction=direction, reason="maximum_trades_reached")
                continue
            if symbol in self._state.active_positions:
                await self.reject_signal(symbol=symbol, direction=direction, reason="position_already_open")
                continue

            entry_price = quote.price
            stop_price = (
                entry_price * (1 - self._stop_pct / 100)
                if direction == "long"
                else entry_price * (1 + self._stop_pct / 100)
            )
            await self.publish_signal(symbol=symbol, direction=direction, entry_price=entry_price, stop_price=stop_price)
            self._trades_today += 1

    async def recover_state(self) -> None:
        """Reload morning bias and determine whether the afternoon entry is
        still valid. Bias itself is derived only from live candles seen
        during the window (never stored history), so after a restart we
        simply trust whatever was captured in MarketState before the
        crash / rely on it being neutral (no trade) if the window was
        missed entirely - conservative by design."""
        logger.info("bias state recovered; known biases=%s", self._state.daily_bias)


def _parse_ts(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)
