from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Bias = Literal["bullish", "bearish", "neutral"]


@dataclass(slots=True)
class Quote:
    symbol: str
    price: float
    bid: float
    ask: float
    timestamp: datetime


@dataclass(slots=True)
class OpeningRange:
    symbol: str
    high: float
    low: float
    midpoint: float
    formed_at: datetime


@dataclass(slots=True)
class NoiseEnvelope:
    symbol: str
    mean: float
    std_dev: float
    atr: float
    upper: float
    lower: float
    updated_at: datetime


@dataclass(slots=True)
class VolumeProfile:
    symbol: str
    # minute-of-session ("09:31") -> average cumulative volume
    average_cumulative_volume: dict[str, float] = field(default_factory=dict)
    today_cumulative_volume: float = 0.0


@dataclass(slots=True)
class AccountSnapshot:
    equity: float = 0.0
    buying_power: float = 0.0
    margin_used: float = 0.0
    cash: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    updated_at: datetime | None = None


class MarketState:
    """The single in-memory runtime object shared by every service and
    strategy. Never persists tick history, historical candles, or trade
    history - that data lives in the database (trades/orders) or is fetched
    fresh from the market data provider on demand / recovery.
    """

    def __init__(self) -> None:
        self.live_quotes: dict[str, Quote] = {}
        self.volume_profiles: dict[str, VolumeProfile] = {}
        self.opening_ranges: dict[str, OpeningRange] = {}
        self.atr: dict[str, float] = {}
        self.noise_boundaries: dict[str, NoiseEnvelope] = {}
        self.daily_bias: dict[str, Bias] = {}
        self.active_orders: dict[str, dict[str, Any]] = {}
        self.active_positions: dict[str, dict[str, Any]] = {}
        self.account_snapshot: AccountSnapshot = AccountSnapshot()
        self.universe: set[str] = set()
        self.qualified_symbols: set[str] = set()
        # Symbols the execution broker can actually trade - populated once
        # at startup (see TradingEngine.start()). Market-data and execution
        # are different providers, so a strategy's dynamically-discovered
        # scan universe must be filtered against this before trading it.
        self.tradeable_symbols: set[str] = set()

    def reset_session(self) -> None:
        """Called at the start of each trading day."""
        self.opening_ranges.clear()
        self.daily_bias.clear()
        self.universe.clear()
        self.qualified_symbols.clear()
        for profile in self.volume_profiles.values():
            profile.today_cumulative_volume = 0.0

    def upsert_quote(self, quote: Quote) -> None:
        self.live_quotes[quote.symbol] = quote

    def upsert_order(self, order_id: str, data: dict[str, Any]) -> None:
        self.active_orders[order_id] = data

    def remove_order(self, order_id: str) -> None:
        self.active_orders.pop(order_id, None)

    def upsert_position(self, symbol: str, data: dict[str, Any]) -> None:
        self.active_positions[symbol] = data

    def remove_position(self, symbol: str) -> None:
        self.active_positions.pop(symbol, None)


market_state = MarketState()
