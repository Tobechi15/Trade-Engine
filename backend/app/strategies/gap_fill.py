from __future__ import annotations

import logging
from datetime import time

from app.core.event_bus import Event
from app.core.events import EventType
from app.core.indicators import BarResampler, atr as compute_atr, parkinson_volatility
from app.core.time_service import TimeService
from app.services.market_data_service import MarketDataService
from app.strategies.base import Strategy

logger = logging.getLogger("strategy")


class OpeningGapFill(Strategy):
    """Conditional Opening Gap Fill. Fades a moderate opening gap (0.15%-
    0.60%) back toward yesterday's close, only when the first 5-minute
    candle confirms a reversal and the volatility regime isn't stressed.

    No $VIX feed is available from Alpaca's stocks API, so the regime
    filter is computed locally instead: 20-day annualized Parkinson
    historical volatility on the target symbol itself (see
    app/core/indicators.py: parkinson_volatility()), gating entries the
    same way a VIX>=25 check would have.

    Daily ATR(14) is used for the stop distance rather than an intraday
    5-minute ATR: at the 09:35 decision point there's only one 5-minute bar
    of the current session, nowhere near enough for an intraday ATR(14) -
    daily bars are fetched once each morning instead."""

    name = "gap_fill"

    def __init__(self, *args, market_data_service: MarketDataService, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._market_data = market_data_service
        self._universe: list[str] = self.config.get("universe", ["SPY", "QQQ"])
        self._min_gap_pct: float = self.config.get("min_gap_pct", 0.0015)
        self._max_gap_pct: float = self.config.get("max_gap_pct", 0.0060)
        self._volatility_threshold: float = self.config.get("volatility_threshold", 0.25)
        self._volatility_window: int = self.config.get("volatility_window", 20)
        self._atr_period: int = self.config.get("atr_period", 14)
        self._partial_fill_fraction: float = self.config.get("partial_fill_fraction", 0.75)
        self._hard_time_stop = _parse_hhmm(self.config.get("hard_time_stop", "11:30"))
        self._max_trades: int = self.config.get("maximum_trades", 2)

        self._resampler = BarResampler(minutes=5)
        self._prior_close: dict[str, float] = {}
        self._daily_atr: dict[str, float] = {}
        self._daily_volatility: dict[str, float] = {}
        self._evaluated_today: set[str] = set()
        self._partial_taken: set[str] = set()
        self._trades_today = 0

    def subscribed_events(self) -> list[EventType]:
        return [EventType.NEW_CANDLE, EventType.MARKET_OPEN, EventType.MARKET_CLOSE]

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        await self._market_data.start_streaming(self._universe)
        await self._prepare_session()

    async def stop(self) -> None:
        pass

    async def _prepare_session(self) -> None:
        history = await self._market_data.get_history(self._universe, days=20, timeframe="1Day")
        for symbol, bars in history.items():
            if len(bars) < 2:
                continue
            self._prior_close[symbol] = bars[-1].close
            atr_value = compute_atr(bars, self._atr_period)
            if atr_value:
                self._daily_atr[symbol] = atr_value
            volatility = parkinson_volatility(bars, self._volatility_window)
            if volatility is not None:
                self._daily_volatility[symbol] = volatility

    async def on_event(self, event: Event) -> None:
        if event.event_type == EventType.MARKET_OPEN:
            self._trades_today = 0
            self._evaluated_today.clear()
            self._partial_taken.clear()
            self._resampler.reset()
            await self._prepare_session()
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
        exchange_time = TimeService.to_exchange(_parse_ts(payload["timestamp"]))

        if generate_signals:
            await self._manage_open_position(symbol, payload, exchange_time)

        completed = self._resampler.add(symbol, payload)
        if completed is None or not generate_signals:
            return
        if symbol in self._evaluated_today:
            return

        open_time = exchange_time.replace(hour=9, minute=30, second=0, microsecond=0)
        first_bucket_end = open_time.replace(minute=35)
        if exchange_time < first_bucket_end:
            return  # first 5-min bucket hasn't closed yet

        self._evaluated_today.add(symbol)
        await self._evaluate_entry(symbol, completed)

    async def _evaluate_entry(self, symbol: str, first_bar) -> None:
        prior_close = self._prior_close.get(symbol)
        if not prior_close:
            return

        volatility = self._daily_volatility.get(symbol)
        if volatility is not None and volatility > self._volatility_threshold:
            return  # elevated volatility regime (Parkinson HV) - sit out
        if volatility is None:
            logger.warning(
                "gap_fill: not enough daily history yet for the Parkinson volatility filter on %s - "
                "proceeding without the regime filter",
                symbol,
            )

        today_open = first_bar.open
        gap_pct = (today_open - prior_close) / prior_close
        bullish = first_bar.close > first_bar.open
        bearish = first_bar.close < first_bar.open

        direction: str | None = None
        if -self._max_gap_pct <= gap_pct <= -self._min_gap_pct and bullish:
            direction = "long"  # gap down, fading back up toward prior close
        elif self._min_gap_pct <= gap_pct <= self._max_gap_pct and bearish:
            direction = "short"  # gap up, fading back down toward prior close
        if direction is None:
            return

        if self._trades_today >= self._max_trades:
            await self.reject_signal(symbol=symbol, direction=direction, reason="maximum_trades_reached")
            return
        if symbol in self._state.active_positions or symbol in self._open_trades:
            await self.reject_signal(symbol=symbol, direction=direction, reason="position_already_open")
            return

        entry_price = first_bar.close
        atr_value = self._daily_atr.get(symbol) or (entry_price * 0.01)
        stop_price = today_open - atr_value if direction == "long" else today_open + atr_value

        await self.publish_signal(
            symbol=symbol, direction=direction, entry_price=entry_price, stop_price=stop_price,
            take_profit_price=prior_close,
        )
        self._trades_today += 1

    async def _manage_open_position(self, symbol: str, payload: dict, exchange_time) -> None:
        position = self._state.active_positions.get(symbol)
        if not position or position.get("strategy") != self.name:
            return

        direction = position.get("direction")
        entry_price = position.get("entry_price")
        prior_close = self._prior_close.get(symbol)
        price = payload["close"]

        if exchange_time.time() >= self._hard_time_stop:
            await self.close_position(symbol, reason="hard_time_stop")
            return

        if entry_price is None or prior_close is None:
            return
        gap_distance = abs(prior_close - entry_price)
        if gap_distance <= 0:
            return
        fill_progress = (
            (price - entry_price) / gap_distance if direction == "long" else (entry_price - price) / gap_distance
        )

        if symbol not in self._partial_taken and fill_progress >= self._partial_fill_fraction:
            self._partial_taken.add(symbol)
            await self.partial_close_position(symbol, fraction=0.5, reason="partial_take_profit")
            return

        if symbol in self._partial_taken:
            # Stop moved to breakeven after the partial: if price gives back
            # to entry, flatten the remainder.
            breakeven_hit = (direction == "long" and price <= entry_price) or (
                direction == "short" and price >= entry_price
            )
            if breakeven_hit:
                await self.close_position(symbol, reason="breakeven_stop")

    async def recover_state(self) -> None:
        await self._prepare_session()
        history = await self._market_data.get_history(self._universe, days=1, timeframe="1Min")
        today = TimeService.now_exchange().date()
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
        logger.info("gap_fill state recovered")


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _parse_ts(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)
