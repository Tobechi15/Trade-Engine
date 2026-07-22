from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.brokers.base import BrokerInterface
from app.core.event_bus import EventBus
from app.core.events import EventType
from app.core.market_state import AccountSnapshot, MarketState
from app.db.base import SessionLocal
from app.db.models import DailyStatistics, Trade

logger = logging.getLogger("system")


class PortfolioManager:
    """Maintains equity, buying power, margin, PnL and daily statistics.
    The account snapshot is refreshed on a scheduled interval; unrealized
    PnL is derived from live positions marked to the latest quote."""

    def __init__(self, event_bus: EventBus, market_state: MarketState, broker: BrokerInterface) -> None:
        self._bus = event_bus
        self._state = market_state
        self._broker = broker
        self._starting_equity_today: float = 0.0

        self._bus.subscribe(EventType.MARKET_OPEN, self._on_market_open)
        self._bus.subscribe(EventType.MARKET_CLOSE, self._on_market_close)

    async def refresh_account(self) -> None:
        try:
            account = await self._broker.get_account()
        except Exception:
            logger.exception("failed to refresh account snapshot")
            return
        snapshot = self._state.account_snapshot
        snapshot.equity = account.equity
        snapshot.buying_power = account.buying_power
        snapshot.cash = account.cash
        snapshot.margin_used = account.margin_used
        snapshot.unrealized_pnl = self.unrealized_pnl()
        snapshot.updated_at = datetime.now(UTC)

    def unrealized_pnl(self) -> float:
        total = 0.0
        for position in self._state.active_positions.values():
            entry = position.get("entry_price") or 0.0
            current = position.get("current_price") or entry
            qty = position.get("quantity", 0.0)
            sign = 1 if position.get("direction") == "long" else -1
            total += sign * (current - entry) * qty
        return total

    def exposure(self) -> dict:
        equity = self._state.account_snapshot.equity or 1.0
        long_notional = sum(
            abs(p["quantity"] * (p.get("current_price") or p["entry_price"]))
            for p in self._state.active_positions.values()
            if p.get("direction") == "long"
        )
        short_notional = sum(
            abs(p["quantity"] * (p.get("current_price") or p["entry_price"]))
            for p in self._state.active_positions.values()
            if p.get("direction") == "short"
        )
        return {
            "long_exposure": long_notional,
            "short_exposure": short_notional,
            "total_exposure_pct": (long_notional + short_notional) / equity * 100,
            "cash": self._state.account_snapshot.cash,
            "margin_used": self._state.account_snapshot.margin_used,
        }

    def get_snapshot(self) -> dict:
        snapshot = self._state.account_snapshot
        return {
            "equity": snapshot.equity,
            "buying_power": snapshot.buying_power,
            "cash": snapshot.cash,
            "margin_used": snapshot.margin_used,
            "unrealized_pnl": self.unrealized_pnl(),
            "realized_pnl_today": snapshot.equity - self._starting_equity_today if self._starting_equity_today else 0.0,
            "open_positions": len(self._state.active_positions),
            "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
            **self.exposure(),
        }

    async def _on_market_open(self, _event) -> None:
        await self.refresh_account()
        self._starting_equity_today = self._state.account_snapshot.equity

    async def _on_market_close(self, _event) -> None:
        await self.refresh_account()
        today = datetime.now(UTC).date().isoformat()
        async with SessionLocal() as session:
            trades_today = (
                await session.execute(
                    select(Trade).where(Trade.exit_time.is_not(None)).where(Trade.exit_time >= datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0))
                )
            ).scalars().all()
            realized = sum(t.pnl or 0.0 for t in trades_today)
            winners = sum(1 for t in trades_today if (t.pnl or 0) > 0)
            losers = sum(1 for t in trades_today if (t.pnl or 0) < 0)

            existing = (
                await session.execute(select(DailyStatistics).where(DailyStatistics.date == today))
            ).scalars().first()
            if existing is None:
                existing = DailyStatistics(date=today)
                session.add(existing)
            existing.starting_equity = self._starting_equity_today
            existing.ending_equity = self._state.account_snapshot.equity
            existing.realized_pnl = realized
            existing.unrealized_pnl = self.unrealized_pnl()
            existing.trades_count = len(trades_today)
            existing.winning_trades = winners
            existing.losing_trades = losers
            await session.commit()
