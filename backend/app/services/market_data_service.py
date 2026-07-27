from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.event_bus import EventBus
from app.core.events import EventType
from app.core.market_state import MarketState, Quote, VolumeProfile
from app.market_data.base import Bar, MarketDataInterface, QuoteTick

logger = logging.getLogger("market_data")


class MarketDataService:
    """Wraps the market data provider: historical fetches, live streaming,
    minute-candle aggregation, and publishing market events. Never stores
    permanent market history - only rolling averages inside MarketState."""

    def __init__(self, event_bus: EventBus, market_state: MarketState, provider: MarketDataInterface) -> None:
        self._bus = event_bus
        self._state = market_state
        self._provider = provider
        self._stream_task: asyncio.Task | None = None
        self._subscribed_symbols: list[str] = []

    @property
    def is_connected(self) -> bool:
        return self._provider.is_connected

    async def connect(self) -> None:
        await self._provider.connect()

    async def get_active_symbols(self, limit: int) -> list[str]:
        return await self._provider.get_active_symbols(limit)

    async def get_index_value(self, index_symbol: str) -> float | None:
        return await self._provider.get_index_value(index_symbol)

    async def disconnect(self) -> None:
        if self._stream_task:
            self._stream_task.cancel()
        await self._provider.disconnect()

    async def get_history(self, symbols: list[str], days: int = 14, timeframe: str = "1Min") -> dict[str, list[Bar]]:
        end = datetime.now(UTC)
        start = end - timedelta(days=int(days * 1.6) + 5)  # pad for weekends/holidays
        bars = await self._provider.get_historical_bars(symbols, start, end, timeframe)
        trading_days_seen: dict[str, set] = {s: set() for s in symbols}
        trimmed: dict[str, list[Bar]] = {}
        for symbol, symbol_bars in bars.items():
            symbol_bars.sort(key=lambda b: b.timestamp)
            kept = []
            for bar in reversed(symbol_bars):
                trading_days_seen.setdefault(symbol, set()).add(bar.timestamp.date())
                if len(trading_days_seen[symbol]) > days:
                    break
                kept.append(bar)
            kept.reverse()
            trimmed[symbol] = kept
        return trimmed

    def build_volume_profile(self, symbol: str, history: list[Bar]) -> VolumeProfile:
        buckets: dict[str, list[float]] = {}
        by_day: dict[object, float] = {}
        for bar in history:
            key = bar.timestamp.strftime("%H:%M")
            day = bar.timestamp.date()
            by_day[day] = by_day.get(day, 0.0) + bar.volume
            buckets.setdefault(key, []).append(by_day[day])
        averages = {minute: sum(values) / len(values) for minute, values in buckets.items()}
        profile = VolumeProfile(symbol=symbol, average_cumulative_volume=averages)
        self._state.volume_profiles[symbol] = profile
        return profile

    async def start_streaming(self, symbols: list[str]) -> None:
        # Merged, never replaced: each strategy calls this independently
        # with only its own symbols, and update_subscriptions() unsubscribes
        # anything not in the list it's given - replacing the tracked set
        # here would drop every previously-subscribed symbol from every
        # other strategy each time a new one starts streaming.
        merged = sorted(set(self._subscribed_symbols) | set(symbols))
        self._subscribed_symbols = merged
        if self._stream_task and not self._stream_task.done():
            await self._provider.update_subscriptions(merged)
            return
        self._stream_task = asyncio.create_task(self._run_stream(), name="market-data-stream")

    async def _run_stream(self) -> None:
        await self._provider.stream(self._subscribed_symbols, self._on_bar, self._on_quote)

    async def _on_bar(self, bar: Bar) -> None:
        profile = self._state.volume_profiles.setdefault(bar.symbol, VolumeProfile(symbol=bar.symbol))
        profile.today_cumulative_volume += bar.volume
        await self._bus.publish(
            EventType.NEW_CANDLE,
            source="market_data",
            payload={
                "symbol": bar.symbol,
                "timestamp": bar.timestamp.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "cumulative_volume": profile.today_cumulative_volume,
            },
        )
        await self._bus.publish(
            EventType.VOLUME_UPDATE,
            source="market_data",
            payload={"symbol": bar.symbol, "cumulative_volume": profile.today_cumulative_volume},
        )

    async def _on_quote(self, quote: QuoteTick) -> None:
        self._state.upsert_quote(
            Quote(symbol=quote.symbol, price=quote.mid, bid=quote.bid, ask=quote.ask, timestamp=quote.timestamp)
        )
        await self._bus.publish(
            EventType.NEW_QUOTE,
            source="market_data",
            payload={
                "symbol": quote.symbol,
                "price": quote.mid,
                "bid": quote.bid,
                "ask": quote.ask,
                "spread_pct": quote.spread_pct,
                "timestamp": quote.timestamp.isoformat(),
            },
        )
