from __future__ import annotations

import logging
from datetime import time

from app.core.event_bus import Event
from app.core.events import EventType
from app.core.indicators import BarResampler, VWAPState, adx as compute_adx, atr as compute_atr
from app.core.time_service import TimeService
from app.market_data.base import Bar
from app.services.market_data_service import MarketDataService
from app.strategies.base import Strategy

logger = logging.getLogger("strategy")


class VwapMeanReversion(Strategy):
    """Intraday VWAP 2-Sigma Mean Reversion. Fades price back toward
    session VWAP when a 5-minute candle pokes outside +/-2 standard
    deviation bands and closes back inside (a rejection candle), gated by
    a non-trending regime filter (ADX < 25)."""

    name = "vwap_reversion"

    def __init__(self, *args, market_data_service: MarketDataService, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._market_data = market_data_service
        self._universe: list[str] = self.config.get("universe", ["SPY", "QQQ"])
        self._num_std: float = self.config.get("num_std", 2.0)
        self._adx_period: int = self.config.get("adx_period", 14)
        self._adx_threshold: float = self.config.get("adx_threshold", 25.0)
        self._atr_period: int = self.config.get("atr_period", 14)
        self._atr_stop_multiplier: float = self.config.get("atr_stop_multiplier", 1.0)
        self._entry_start = _parse_hhmm(self.config.get("entry_start", "10:00"))
        self._entry_end = _parse_hhmm(self.config.get("entry_end", "15:00"))
        self._time_exit = _parse_hhmm(self.config.get("time_exit", "15:45"))
        self._max_trades: int = self.config.get("maximum_trades", 6)

        self._resampler = BarResampler(minutes=5)
        self._vwap: dict[str, VWAPState] = {}
        self._bars5m: dict[str, list[Bar]] = {}
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
        await self._check_time_exit(symbol, exchange_time)
        await self._check_vwap_target(symbol)
        await self._evaluate_entry(symbol, bar, exchange_time)

    async def _check_time_exit(self, symbol: str, exchange_time) -> None:
        if exchange_time.time() < self._time_exit:
            return
        position = self._state.active_positions.get(symbol)
        if position and position.get("strategy") == self.name:
            await self.close_position(symbol, reason="time_exit")

    async def _check_vwap_target(self, symbol: str) -> None:
        position = self._state.active_positions.get(symbol)
        if not position or position.get("strategy") != self.name:
            return
        vwap = self._vwap[symbol].vwap
        price = position.get("current_price")
        if not price or not vwap:
            return
        direction = position.get("direction")
        reached = (direction == "long" and price >= vwap) or (direction == "short" and price <= vwap)
        if reached:
            await self.close_position(symbol, reason="vwap_target")

    async def _evaluate_entry(self, symbol: str, prev_bar: Bar, exchange_time) -> None:
        if not (self._entry_start <= exchange_time.time() <= self._entry_end):
            return
        if self._trades_today >= self._max_trades:
            return
        if symbol in self._state.active_positions or symbol in self._open_trades:
            return

        bars = self._bars5m.get(symbol, [])
        adx_value = compute_adx(bars, self._adx_period)
        if adx_value is None or adx_value >= self._adx_threshold:
            return  # trending regime - sit out

        vwap_state = self._vwap[symbol]
        upper, lower = vwap_state.band(self._num_std)

        direction: str | None = None
        if prev_bar.low <= lower and prev_bar.close > lower:
            direction = "long"
        elif prev_bar.high >= upper and prev_bar.close < upper:
            direction = "short"
        if direction is None:
            return

        entry_price = prev_bar.close
        atr_value = compute_atr(bars, self._atr_period) or (entry_price * 0.003)
        stop_price = (
            entry_price - atr_value * self._atr_stop_multiplier
            if direction == "long"
            else entry_price + atr_value * self._atr_stop_multiplier
        )
        take_profit_price = vwap_state.vwap

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
        logger.info("vwap_reversion state recovered")


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _parse_ts(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)
