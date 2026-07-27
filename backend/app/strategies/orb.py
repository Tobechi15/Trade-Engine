from __future__ import annotations

import logging
from datetime import timedelta

from app.core.event_bus import Event
from app.core.events import EventType
from app.core.market_state import OpeningRange
from app.core.time_service import TimeService
from app.services.market_data_service import MarketDataService
from app.strategies.base import Strategy

logger = logging.getLogger("strategy")

# NOTE: the stack has no dedicated news/unusual-activity feed. Universe
# selection ranks a candidate pool by premarket gap % and premarket volume
# (both derivable from Bybit klines) plus a liquidity floor. News-catalyst /
# unusual-activity scoring are left as pluggable, zero-weight hooks until
# such a data source is wired in.
#
# By default the candidate pool itself is fetched dynamically each morning
# via MarketDataService.get_active_symbols() (Bybit TradFi's top symbols by
# 24h turnover - see app/market_data/bybit.py), not hardcoded. Set
# `candidate_symbols` in app/data/strategies.yaml to pin a fixed list
# instead (e.g. for backtesting reproducibility). DEFAULT_CANDIDATES below
# is only the fallback used if dynamic discovery fails.
DEFAULT_CANDIDATES = [
    "AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "META", "ORCL", "INTC", "TSM",
    "MU", "SNDK", "CRCL", "MSTR", "COIN", "HOOD", "SPY", "QQQ", "EWJ", "EWY",
]


class OpeningRangeBreakout(Strategy):
    name = "orb"

    def __init__(self, *args, market_data_service: MarketDataService, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._market_data = market_data_service
        self._rvol_threshold: float = self.config.get("rvol_threshold", 3)
        self._universe_size: int = self.config.get("universe_size", 40)
        self._or_minutes: int = self.config.get("opening_range", 5)
        self._max_spread: float = self.config.get("maximum_spread", 0.15)
        self._reward_risk_ratio: float = self.config.get("reward_risk_ratio", 2.0)
        self._max_trades: int = self.config.get("maximum_trades", 10)
        # None (the default) means "fetch the top-active candidate pool
        # dynamically each morning"; set explicitly to pin a fixed list.
        self._candidate_symbols: list[str] | None = self.config.get("candidate_symbols")
        self._candidate_pool_size: int = self.config.get("candidate_pool_size", 30)
        # Bybit TradFi perpetual volume is contract count, not underlying
        # share volume, and is far thinner than NYSE/Nasdaq consolidated
        # tape - this default is a placeholder to tune empirically once
        # live volume on these instruments has been observed.
        self._min_premarket_volume: float = self.config.get("min_premarket_volume", 1_000)

        self._trades_today = 0
        self._or_builder: dict[str, dict[str, float]] = {}

    def subscribed_events(self) -> list[EventType]:
        return [EventType.NEW_CANDLE, EventType.MARKET_OPEN, EventType.MARKET_CLOSE]

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        await self.build_universe()

    async def stop(self) -> None:
        pass

    async def build_universe(self) -> None:
        """Runs before market open (scheduled by the engine). Scans the
        candidate pool, ranks by premarket gap % and volume, and selects
        ~30-40 symbols as today's trading universe."""
        if self._candidate_symbols is not None:
            candidates = self._candidate_symbols
        else:
            candidates = await self._market_data.get_active_symbols(self._candidate_pool_size)
            # Market data (Alpaca) covers far more symbols than the
            # execution broker (Bybit) can actually trade - never scan a
            # symbol we can't place an order for.
            tradeable = self._state.tradeable_symbols
            if tradeable:
                candidates = [s for s in candidates if s in tradeable]
        history = await self._market_data.get_history(candidates, days=14)
        scored: list[tuple[str, float]] = []
        for symbol, bars in history.items():
            if len(bars) < 20:
                continue
            self._market_data.build_volume_profile(symbol, bars)

            by_day: dict = {}
            for bar in bars:
                by_day.setdefault(bar.timestamp.date(), []).append(bar)
            days_sorted = sorted(by_day.keys())
            if len(days_sorted) < 2:
                continue
            today_bars = by_day[days_sorted[-1]]
            prior_close = by_day[days_sorted[-2]][-1].close
            first_price = today_bars[0].open
            if prior_close <= 0:
                continue
            gap_pct = abs(first_price - prior_close) / prior_close * 100
            premarket_volume = sum(b.volume for b in today_bars)
            if premarket_volume < self._min_premarket_volume:
                continue
            score = gap_pct * (premarket_volume**0.5)
            scored.append((symbol, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        universe = [symbol for symbol, _ in scored[: self._universe_size]]
        self._state.universe = set(universe)
        self._state.qualified_symbols = set(universe)
        if universe:
            await self._market_data.start_streaming(universe)
        logger.info("orb universe built size=%d", len(universe))

    async def on_event(self, event: Event) -> None:
        if event.event_type == EventType.MARKET_OPEN:
            self._state.reset_session()
            self._trades_today = 0
            self._or_builder.clear()
            await self.build_universe()
        elif event.event_type == EventType.NEW_CANDLE:
            await self._process_bar(event.payload, generate_signals=True)
        elif event.event_type == EventType.MARKET_CLOSE:
            for symbol, position in list(self._state.active_positions.items()):
                if position.get("strategy") == self.name:
                    await self.close_position(symbol, reason="eod_exit")

    async def _process_bar(self, payload: dict, *, generate_signals: bool) -> None:
        symbol = payload["symbol"]
        if symbol not in self._state.qualified_symbols:
            return

        exchange_time = TimeService.to_exchange(_parse_ts(payload["timestamp"]))
        open_time = exchange_time.replace(hour=9, minute=30, second=0, microsecond=0)
        or_end = open_time + timedelta(minutes=self._or_minutes)

        if exchange_time < or_end:
            builder = self._or_builder.setdefault(symbol, {"high": float("-inf"), "low": float("inf")})
            builder["high"] = max(builder["high"], payload["high"])
            builder["low"] = min(builder["low"], payload["low"])
            return

        if symbol not in self._state.opening_ranges:
            builder = self._or_builder.get(symbol)
            if not builder or builder["high"] == float("-inf"):
                return
            midpoint = (builder["high"] + builder["low"]) / 2
            self._state.opening_ranges[symbol] = OpeningRange(
                symbol=symbol, high=builder["high"], low=builder["low"], midpoint=midpoint, formed_at=exchange_time
            )
            await self._bus.publish(
                EventType.OPENING_RANGE_READY,
                source=self.name,
                payload={"symbol": symbol, "high": builder["high"], "low": builder["low"], "midpoint": midpoint},
            )
            return

        if not generate_signals:
            return
        await self._evaluate_breakout(symbol, payload, exchange_time)

    async def _evaluate_breakout(self, symbol: str, payload: dict, exchange_time) -> None:
        opening_range = self._state.opening_ranges[symbol]
        profile = self._state.volume_profiles.get(symbol)
        rvol = None
        if profile:
            avg = profile.average_cumulative_volume.get(exchange_time.strftime("%H:%M"))
            if avg:
                rvol = profile.today_cumulative_volume / avg
        if rvol is None or rvol < self._rvol_threshold:
            return

        quote = self._state.live_quotes.get(symbol)
        if quote and quote.price:
            spread_pct = (quote.ask - quote.bid) / quote.price * 100
            if spread_pct > self._max_spread:
                return

        price = payload["close"]
        direction: str | None = None
        stop = 0.0
        if price > opening_range.high:
            direction, stop = "long", opening_range.low
        elif price < opening_range.low:
            direction, stop = "short", opening_range.high
        if direction is None:
            return

        if self._trades_today >= self._max_trades:
            await self.reject_signal(symbol=symbol, direction=direction, reason="maximum_trades_reached")
            return
        if symbol in self._state.active_positions or symbol in self._open_trades:
            await self.reject_signal(symbol=symbol, direction=direction, reason="position_already_open")
            return

        risk_distance = abs(price - stop)
        take_profit = (
            price + risk_distance * self._reward_risk_ratio
            if direction == "long"
            else price - risk_distance * self._reward_risk_ratio
        )
        await self.publish_signal(
            symbol=symbol, direction=direction, entry_price=price, stop_price=stop, take_profit_price=take_profit
        )
        self._trades_today += 1

    async def recover_state(self) -> None:
        if not self._state.universe:
            await self.build_universe()
        symbols = list(self._state.universe)
        if not symbols:
            return
        history = await self._market_data.get_history(symbols, days=1, timeframe="1Min")
        today = TimeService.now_exchange().date()
        for symbol, bars in history.items():
            for bar in sorted(bars, key=lambda b: b.timestamp):
                if TimeService.to_exchange(bar.timestamp).date() != today:
                    continue
                profile = self._state.volume_profiles.get(symbol)
                if profile is None:
                    profile = self._market_data.build_volume_profile(symbol, [])
                profile.today_cumulative_volume += bar.volume
                await self._process_bar(
                    {
                        "symbol": symbol,
                        "timestamp": bar.timestamp.isoformat(),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    },
                    generate_signals=False,
                )
        await self._market_data.start_streaming(symbols)
        logger.info("orb state recovered")


def _parse_ts(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)
