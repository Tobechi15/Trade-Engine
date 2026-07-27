from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from app.brokers.base import (
    BrokerAccount,
    BrokerInterface,
    BrokerOrder,
    BrokerPosition,
    FillCallback,
    OrderRequest,
)
from app.config import Settings
from app.core.market_state import MarketState

logger = logging.getLogger("broker")

# Delay between place_order() returning and delivering the simulated fill.
# OrderManager._submit() writes the Order row to the DB right after
# place_order() returns; handle_fill() looks that row up and no-ops if it
# isn't there yet, so the fill must be delivered on a later loop iteration
# rather than inline.
_FILL_DELAY_SECONDS = 0.05


@dataclass
class _PaperPosition:
    symbol: str
    side: str  # "long" | "short"
    quantity: float
    avg_entry_price: float


class PaperTradingBroker(BrokerInterface):
    """Wraps a real broker for read-only reference data (tradeable symbols)
    while simulating every order locally against a virtual balance. Lets a
    mainnet-only API key run the engine without ever placing a live order -
    Bybit's demo trading environment needs its own demo-specific keys, which
    isn't what this is for (see Settings.paper_trading)."""

    def __init__(self, settings: Settings, market_state: MarketState, reference_broker: BrokerInterface) -> None:
        self._settings = settings
        self._state = market_state
        self._reference_broker = reference_broker
        self._connected = False
        self._on_fill: FillCallback | None = None
        self._positions: dict[str, _PaperPosition] = {}
        self._realized_pnl = 0.0

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True
        logger.warning(
            "PAPER TRADING MODE active - orders are simulated locally with a virtual balance of %.2f, "
            "nothing is sent to Bybit",
            self._settings.paper_starting_equity,
        )

    async def disconnect(self) -> None:
        self._connected = False
        await self._reference_broker.disconnect()

    def _mark_price(self, symbol: str, fallback: float) -> float:
        quote = self._state.live_quotes.get(symbol)
        return quote.price if quote and quote.price else fallback

    def _apply_fill(self, request: OrderRequest, fill_price: float) -> None:
        is_buy = request.side == "buy"
        pos = self._positions.get(request.symbol)
        if pos is None:
            self._positions[request.symbol] = _PaperPosition(
                symbol=request.symbol,
                side="long" if is_buy else "short",
                quantity=request.quantity,
                avg_entry_price=fill_price,
            )
            return

        same_direction = (pos.side == "long") == is_buy
        if same_direction:
            total_qty = pos.quantity + request.quantity
            pos.avg_entry_price = (pos.avg_entry_price * pos.quantity + fill_price * request.quantity) / total_qty
            pos.quantity = total_qty
            return

        closing_qty = min(pos.quantity, request.quantity)
        pnl_per_unit = (fill_price - pos.avg_entry_price) if pos.side == "long" else (pos.avg_entry_price - fill_price)
        self._realized_pnl += pnl_per_unit * closing_qty
        remaining = pos.quantity - closing_qty
        leftover = request.quantity - closing_qty
        if remaining > 1e-9:
            pos.quantity = remaining
        elif leftover > 1e-9:
            self._positions[request.symbol] = _PaperPosition(
                symbol=request.symbol, side="long" if is_buy else "short", quantity=leftover, avg_entry_price=fill_price
            )
        else:
            del self._positions[request.symbol]

    async def _deliver_fill(self, order: BrokerOrder) -> None:
        await asyncio.sleep(_FILL_DELAY_SECONDS)
        if self._on_fill:
            await self._on_fill(order)

    async def place_order(self, request: OrderRequest) -> BrokerOrder:
        fill_price = request.limit_price if request.order_type == "limit" and request.limit_price else None
        fill_price = self._mark_price(request.symbol, fill_price or 0.0)
        self._apply_fill(request, fill_price)

        order_id = f"paper-{uuid.uuid4().hex[:16]}"
        submitted = BrokerOrder(
            broker_order_id=order_id,
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled_quantity=0.0,
            status="submitted",
        )
        filled = BrokerOrder(
            broker_order_id=order_id,
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled_quantity=request.quantity,
            status="filled",
            avg_fill_price=fill_price,
        )
        asyncio.create_task(self._deliver_fill(filled))
        return submitted

    async def cancel_order(self, broker_order_id: str) -> None:
        # Simulated orders fill synchronously in place_order() - there is
        # never anything resting to cancel.
        return

    async def modify_order(
        self,
        broker_order_id: str,
        *,
        quantity: float | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> BrokerOrder:
        raise NotImplementedError("paper trading fills orders immediately - there is nothing to modify")

    async def get_open_orders(self) -> list[BrokerOrder]:
        return []

    async def get_tradeable_symbols(self) -> set[str]:
        return await self._reference_broker.get_tradeable_symbols()

    async def get_positions(self) -> list[BrokerPosition]:
        positions = []
        for pos in self._positions.values():
            mark = self._mark_price(pos.symbol, pos.avg_entry_price)
            unrealized = (mark - pos.avg_entry_price) * pos.quantity
            if pos.side == "short":
                unrealized = -unrealized
            positions.append(
                BrokerPosition(
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    side=pos.side,
                    avg_entry_price=pos.avg_entry_price,
                    unrealized_pnl=unrealized,
                )
            )
        return positions

    async def get_account(self) -> BrokerAccount:
        unrealized_total = sum(p.unrealized_pnl for p in await self.get_positions())
        cash = self._settings.paper_starting_equity + self._realized_pnl
        equity = cash + unrealized_total
        return BrokerAccount(equity=equity, buying_power=equity, cash=cash, margin_used=0.0)

    async def get_balances(self) -> dict[str, float]:
        account = await self.get_account()
        return {"cash": account.cash, "equity": account.equity}

    async def stream_fills(self, on_fill: FillCallback) -> None:
        self._on_fill = on_fill
        self._connected = True
        # No real stream to listen to - place_order() delivers fills
        # directly. Block forever so RecoveryService's supervisor treats
        # this the same as a persistently healthy connection instead of
        # busy-looping on a stream that returns immediately.
        await asyncio.Event().wait()
