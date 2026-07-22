from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import polars as pl
from sqlalchemy import select

from app.core.event_bus import Event, EventBus
from app.core.events import EventType
from app.db.base import SessionLocal
from app.db.models import StrategyPerformance, Trade


class AnalyticsService:
    """Collects win rate, profit factor, Sharpe ratio, drawdown,
    expectancy, average winner/loser, monthly returns and the equity curve
    - both overall and per strategy."""

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._bus.subscribe(EventType.TRADE_ENTERED, self._on_trade_entered)
        self._bus.subscribe(EventType.TRADE_EXITED, self._on_trade_exited)

    async def _on_trade_entered(self, event: Event) -> None:
        payload = event.payload
        async with SessionLocal() as session:
            session.add(
                Trade(
                    strategy=payload["strategy"],
                    symbol=payload["symbol"],
                    direction=payload["direction"],
                    signal_time=datetime.fromisoformat(payload["signal_time"]),
                    entry_time=datetime.fromisoformat(payload["entry_time"]) if payload.get("entry_time") else None,
                    entry_price=payload.get("entry_price"),
                    quantity=payload.get("quantity") or 0.0,
                    risk_amount=abs((payload.get("entry_price") or 0) - (payload.get("stop_price") or 0)) * (payload.get("quantity") or 0),
                )
            )
            await session.commit()

    async def _on_trade_exited(self, event: Event) -> None:
        payload = event.payload
        async with SessionLocal() as session:
            row = (
                await session.execute(
                    select(Trade)
                    .where(Trade.strategy == payload["strategy"])
                    .where(Trade.symbol == payload["symbol"])
                    .where(Trade.exit_time.is_(None))
                    .order_by(Trade.created_at.desc())
                )
            ).scalars().first()
            if row is None:
                return
            row.exit_time = datetime.fromisoformat(payload["exit_time"]) if payload.get("exit_time") else datetime.now(UTC)
            row.exit_price = payload.get("exit_price")
            row.pnl = payload.get("pnl")
            row.r_multiple = payload.get("r_multiple")
            row.duration_seconds = payload.get("duration_seconds")
            row.exit_reason = payload.get("exit_reason")
            await session.commit()
        await self.recompute_strategy_performance(payload["strategy"])

    async def recompute_strategy_performance(self, strategy: str) -> None:
        async with SessionLocal() as session:
            trades = (
                await session.execute(
                    select(Trade).where(Trade.strategy == strategy).where(Trade.exit_time.is_not(None))
                )
            ).scalars().all()
            metrics = compute_metrics([t.pnl or 0.0 for t in trades], [t.duration_seconds or 0 for t in trades])

            row = (
                await session.execute(select(StrategyPerformance).where(StrategyPerformance.strategy == strategy))
            ).scalars().first()
            if row is None:
                row = StrategyPerformance(strategy=strategy)
                session.add(row)
            row.total_trades = metrics["total_trades"]
            row.winning_trades = metrics["winning_trades"]
            row.losing_trades = metrics["losing_trades"]
            row.win_rate = metrics["win_rate"]
            row.profit_factor = metrics["profit_factor"]
            row.sharpe_ratio = metrics["sharpe_ratio"]
            row.max_drawdown = metrics["max_drawdown"]
            row.expectancy = metrics["expectancy"]
            row.average_winner = metrics["average_winner"]
            row.average_loser = metrics["average_loser"]
            row.average_hold_time_seconds = metrics["average_hold_time_seconds"]
            await session.commit()

    async def overview(self) -> dict:
        async with SessionLocal() as session:
            trades = (
                await session.execute(select(Trade).where(Trade.exit_time.is_not(None)))
            ).scalars().all()
        return compute_metrics([t.pnl or 0.0 for t in trades], [t.duration_seconds or 0 for t in trades])

    async def equity_curve(self) -> list[dict]:
        async with SessionLocal() as session:
            trades = (
                await session.execute(
                    select(Trade).where(Trade.exit_time.is_not(None)).order_by(Trade.exit_time)
                )
            ).scalars().all()
        if not trades:
            return []
        df = pl.DataFrame({"exit_time": [t.exit_time for t in trades], "pnl": [t.pnl or 0.0 for t in trades]})
        df = df.with_columns(pl.col("pnl").cum_sum().alias("equity"))
        return [{"time": row["exit_time"].isoformat(), "equity": row["equity"]} for row in df.to_dicts()]

    async def monthly_returns(self) -> list[dict]:
        async with SessionLocal() as session:
            trades = (
                await session.execute(select(Trade).where(Trade.exit_time.is_not(None)))
            ).scalars().all()
        if not trades:
            return []
        df = pl.DataFrame({"exit_time": [t.exit_time for t in trades], "pnl": [t.pnl or 0.0 for t in trades]})
        df = df.with_columns(pl.col("exit_time").dt.strftime("%Y-%m").alias("month"))
        grouped = df.group_by("month").agg(pl.col("pnl").sum().alias("pnl")).sort("month")
        return grouped.to_dicts()

    async def trades(self, *, strategy: str | None = None, limit: int = 200) -> list[dict]:
        async with SessionLocal() as session:
            query = select(Trade).order_by(Trade.created_at.desc()).limit(limit)
            if strategy:
                query = query.where(Trade.strategy == strategy)
            rows = (await session.execute(query)).scalars().all()
        return [
            {
                "id": t.id,
                "strategy": t.strategy,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl": t.pnl,
                "r_multiple": t.r_multiple,
                "exit_reason": t.exit_reason,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            }
            for t in rows
        ]


def compute_metrics(pnls: list[float], durations: list[float]) -> dict:
    total = len(pnls)
    if total == 0:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0, "win_rate": 0.0,
            "profit_factor": 0.0, "sharpe_ratio": 0.0, "max_drawdown": 0.0, "expectancy": 0.0,
            "average_winner": 0.0, "average_loser": 0.0, "average_hold_time_seconds": 0.0,
        }
    arr = np.array(pnls, dtype=float)
    winners = arr[arr > 0]
    losers = arr[arr < 0]
    gross_profit = winners.sum() if winners.size else 0.0
    gross_loss = abs(losers.sum()) if losers.size else 0.0
    equity_curve = np.cumsum(arr)
    running_max = np.maximum.accumulate(equity_curve) if equity_curve.size else np.array([0.0])
    drawdown = running_max - equity_curve
    returns_std = arr.std(ddof=1) if arr.size > 1 else 0.0

    return {
        "total_trades": total,
        "winning_trades": int(winners.size),
        "losing_trades": int(losers.size),
        "win_rate": float(winners.size / total * 100),
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0,
        "sharpe_ratio": float(arr.mean() / returns_std * (252**0.5)) if returns_std > 0 else 0.0,
        "max_drawdown": float(drawdown.max()) if drawdown.size else 0.0,
        "expectancy": float(arr.mean()),
        "average_winner": float(winners.mean()) if winners.size else 0.0,
        "average_loser": float(losers.mean()) if losers.size else 0.0,
        "average_hold_time_seconds": float(np.mean(durations)) if durations else 0.0,
    }
