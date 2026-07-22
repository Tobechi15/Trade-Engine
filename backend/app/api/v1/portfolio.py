from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import get_current_user, get_engine
from app.db.base import SessionLocal
from app.db.models import DailyStatistics
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"], dependencies=[Depends(get_current_user)])


@router.get("")
async def portfolio(engine: TradingEngine = Depends(get_engine)):
    return ok(engine.portfolio_manager.get_snapshot())


@router.get("/exposure")
async def exposure(engine: TradingEngine = Depends(get_engine)):
    return ok(engine.portfolio_manager.exposure())


@router.get("/statistics")
async def statistics(limit: int = 30):
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(DailyStatistics).order_by(DailyStatistics.date.desc()).limit(limit))
        ).scalars().all()
    return ok(
        [
            {
                "date": r.date,
                "starting_equity": r.starting_equity,
                "ending_equity": r.ending_equity,
                "realized_pnl": r.realized_pnl,
                "unrealized_pnl": r.unrealized_pnl,
                "trades_count": r.trades_count,
                "winning_trades": r.winning_trades,
                "losing_trades": r.losing_trades,
                "max_drawdown": r.max_drawdown,
            }
            for r in rows
        ]
    )
