from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class QuoteTick:
    symbol: str
    bid: float
    ask: float
    timestamp: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> float:
        if self.mid == 0:
            return 0.0
        return (self.ask - self.bid) / self.mid * 100


BarCallback = Callable[[Bar], Awaitable[None]]
QuoteCallback = Callable[[QuoteTick], Awaitable[None]]


class MarketDataInterface(ABC):
    """Abstraction the Market Data Service codes against. Strategies never
    talk to a market data provider directly."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_historical_bars(
        self, symbols: list[str], start: datetime, end: datetime, timeframe: str = "1Min"
    ) -> dict[str, list[Bar]]: ...

    @abstractmethod
    async def stream(self, symbols: list[str], on_bar: BarCallback, on_quote: QuoteCallback) -> None:
        """Long-running task: streams live bars/quotes for the given
        symbols. Must be cancellation-safe; raises on disconnect so a
        supervisor (Recovery Service) can restart it with backoff."""
        ...

    @abstractmethod
    async def update_subscriptions(self, symbols: list[str]) -> None: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...
