from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = "market"
    limit_price: float | None = None
    stop_price: float | None = None
    take_profit_price: float | None = None
    client_order_id: str | None = None


@dataclass(slots=True)
class BrokerOrder:
    broker_order_id: str
    client_order_id: str | None
    symbol: str
    side: OrderSide
    quantity: float
    filled_quantity: float
    status: str
    avg_fill_price: float | None = None


@dataclass(slots=True)
class BrokerPosition:
    symbol: str
    quantity: float
    side: Literal["long", "short"]
    avg_entry_price: float
    unrealized_pnl: float


@dataclass(slots=True)
class BrokerAccount:
    equity: float
    buying_power: float
    cash: float
    margin_used: float


FillCallback = Callable[[BrokerOrder], Awaitable[None]]


class BrokerInterface(ABC):
    """Abstraction every strategy/service codes against. Strategies never
    talk to a broker directly - only the Order Manager, through this
    interface. Swapping brokers should only require a new adapter class."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> BrokerOrder: ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> None: ...

    @abstractmethod
    async def modify_order(
        self,
        broker_order_id: str,
        *,
        quantity: float | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> BrokerOrder: ...

    @abstractmethod
    async def get_open_orders(self) -> list[BrokerOrder]: ...

    @abstractmethod
    async def get_tradeable_symbols(self) -> set[str]:
        """The full set of symbols this broker can actually execute orders
        for. Needed because a strategy's scan universe may come from a
        market-data provider with broader coverage than the execution
        broker - the engine intersects the two before a strategy trades
        anything it discovered dynamically."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    async def get_account(self) -> BrokerAccount: ...

    @abstractmethod
    async def get_balances(self) -> dict[str, float]: ...

    @abstractmethod
    async def stream_fills(self, on_fill: FillCallback) -> None:
        """Long-running task: subscribes to the private order/fill stream
        and invokes on_fill for every fill/status change. Must be
        cancellation-safe (used inside an asyncio.Task the Recovery
        Service can restart)."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...
