from __future__ import annotations

import logging
from datetime import time

from app.core.event_bus import Event
from app.core.events import EventType
from app.core.indicators import BarResampler, VWAPState, atr as compute_atr
from app.core.time_service import TimeService
from app.market_data.base import Bar
from app.services.market_data_service import MarketDataService
from app.strategies.base import Strategy

logger = logging.getLogger("strategy")


class BreadthVwapPullback(Strategy):
    """Breadth-Filtered VWAP Pullback. Trend-continuation entries on a
    shallow pullback to session VWAP, gated by NYSE breadth ($ADD) and
    the symbol's own position relative to its VWAP.

    NYSE $ADD (advance-decline breadth) availability from the market data
    provider is unconfirmed (see app/market_data/massive.py). If it's
    unavailable, get_index_value() returns None and this strategy sits out
    entirely rather than trading without the breadth filter - "no data"
    must never be treated as "condition satisfied"."""

    name = "breadth_pullback"

    def __init__(self, *args, market_data_service: MarketDataService, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._market_data = market_data_service
        self._universe: list[str] = self.config.get("universe", ["SPY", "QQQ"])
        self._breadth_threshold: float = self.config.get("breadth_threshold", 1000.0)
        self._atr_period: int = self.config.get("atr_period", 14)
        self._atr_multiplier: float = self.config.get("atr_multiplier", 1.2)
        self._reward_risk_ratio: float = self.config.get("reward_risk_ratio", 2.0)
        self._entry_start = _parse_hhmm(self.config.get("entry_start", "10:00"))
        self._entry_end = _parse_hhmm(self.config.get("entry_end", "14:30"))
        self._time_exit = _parse_hhmm(self.config.get("time_exit", "15:45"))
        self._max_trades: int = self.config.get("maximum_trades", 4)

        self._resampler = BarResampler(minutes=5)
        self._vwap: dict[str, VWAPState] = {}
        self._bars5m: dict[str, list[Bar]] = {}
        self._session_high: dict[str, float] = {}
        self._session_low: dict[str, float] = {}
        self._breadth_unavailable_logged = False
        self._trades_today = 0

    def subscribed_events(self) -> list[EventType]:
        return [EventType.NEW_CANDLE, EventType.MARKET_OPEN, EventType.MARKET_CLOSE]

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        await self._market_data.start_streaming(self._universe)

    async def stop(self) -> None:
        pass

    async def on_event(self, event: Event) -> None:
        if event.event_type == EventType.MARKET_OPEN:
            self._trades_today = 0
            self._resampler.reset()
            self._vwap = {s: VWAPState() for s in self._universe}
            self._bars5m = {s: [] for s in self._universe}
            self._session_high = {}
            self._session_low = {}
        elif event.event_type == EventType.NEW_CANDLE:
            await self._on_candle(event.payload, generate_signals=True)
        elif event.event_type == EventType.MARKET_CLOSE:
            for symbol, position in list(self._state.active_positions.items()):
                if position.get("strategy") == self.name:
                    await self.close_position(symbol, reason="eod_exit")

    async def _on_candle(self, payload: dict, *, generate_signals: bool) -> None:
        symbol = payload["symbol"]
        if symbol not in self._universe:
            return

        typical_price = (payload["high"] + payload["low"] + payload["close"]) / 3
        self._vwap.setdefault(symbol, VWAPState()).update(typical_price, payload["volume"])
        self._session_high[symbol] = max(self._session_high.get(symbol, payload["high"]), payload["high"])
        self._session_low[symbol] = min(self._session_low.get(symbol, payload["low"]), payload["low"])

        exchange_time = TimeService.to_exchange(_parse_ts(payload["timestamp"]))

        completed = self._resampler.add(symbol, payload)
        if completed is None:
            return
        bar = completed.to_bar(symbol)
        bars = self._bars5m.setdefault(symbol, [])
        bars.append(bar)
        self._bars5m[symbol] = bars[-200:]

        if not generate_signals:
            return

        if exchange_time.time() >= self._time_exit:
            position = self._state.active_positions.get(symbol)
            if position and position.get("strategy") == self.name:
                await self.close_position(symbol, reason="time_exit")
            return

        await self._evaluate_entry(symbol, bar, exchange_time)

    async def _evaluate_entry(self, symbol: str, bar: Bar, exchange_time) -> None:
        if not (self._entry_start <= exchange_time.time() <= self._entry_end):
            return
        if self._trades_today >= self._max_trades:
            return
        if symbol in self._state.active_positions or symbol in self._open_trades:
            return

        breadth = await self._market_data.get_index_value("ADD")
        if breadth is None:
            if not self._breadth_unavailable_logged:
                logger.warning(
                    "breadth_pullback: NYSE $ADD breadth data unavailable from the market data "
                    "provider - sitting out rather than trading without the breadth filter"
                )
                self._breadth_unavailable_logged = True
            return

        vwap_state = self._vwap[symbol]
        vwap = vwap_state.vwap
        if not vwap:
            return

        direction: str | None = None
        if breadth > self._breadth_threshold and bar.close > vwap and bar.low <= vwap and bar.close > vwap:
            direction = "long"
        elif breadth < -self._breadth_threshold and bar.close < vwap and bar.high >= vwap and bar.close < vwap:
            direction = "short"
        if direction is None:
            return

        bars = self._bars5m.get(symbol, [])
        atr_value = compute_atr(bars, self._atr_period) or (bar.close * 0.003)
        entry_price = bar.close
        stop_price = (
            vwap - atr_value * self._atr_multiplier if direction == "long" else vwap + atr_value * self._atr_multiplier
        )
        risk_distance = abs(entry_price - stop_price)
        rr_target = (
            entry_price + risk_distance * self._reward_risk_ratio
            if direction == "long"
            else entry_price - risk_distance * self._reward_risk_ratio
        )
        structural_target = self._session_high.get(symbol) if direction == "long" else self._session_low.get(symbol)
        if direction == "long":
            take_profit_price = max(rr_target, structural_target or rr_target)
        else:
            take_profit_price = min(rr_target, structural_target or rr_target)

        await self.publish_signal(
            symbol=symbol, direction=direction, entry_price=entry_price, stop_price=stop_price,
            take_profit_price=take_profit_price,
        )
        self._trades_today += 1

    async def recover_state(self) -> None:
        history = await self._market_data.get_history(self._universe, days=1, timeframe="1Min")
        today = TimeService.now_exchange().date()
        self._vwap = {s: VWAPState() for s in self._universe}
        self._bars5m = {s: [] for s in self._universe}
        self._session_high = {}
        self._session_low = {}
        self._resampler.reset()
        for symbol, bars in history.items():
            for bar in sorted(bars, key=lambda b: b.timestamp):
                if TimeService.to_exchange(bar.timestamp).date() != today:
                    continue
                await self._on_candle(
                    {
                        "symbol": symbol, "timestamp": bar.timestamp.isoformat(),
                        "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume,
                    },
                    generate_signals=False,
                )
        await self._market_data.start_streaming(self._universe)
        logger.info("breadth_pullback state recovered")


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _parse_ts(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)
