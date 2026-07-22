from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_engine
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])


@router.get("")
async def analytics_overview(engine: TradingEngine = Depends(get_engine)):
    return ok(await engine.analytics_service.overview())


@router.get("/equity-curve")
async def equity_curve(engine: TradingEngine = Depends(get_engine)):
    return ok(await engine.analytics_service.equity_curve())


@router.get("/monthly")
async def monthly(engine: TradingEngine = Depends(get_engine)):
    return ok(await engine.analytics_service.monthly_returns())


@router.get("/strategy/{strategy}")
async def strategy_analytics(strategy: str, engine: TradingEngine = Depends(get_engine)):
    trades = await engine.analytics_service.trades(strategy=strategy)
    from app.services.analytics_service import compute_metrics

    metrics = compute_metrics([t["pnl"] or 0.0 for t in trades], [0.0 for _ in trades])
    return ok({"strategy": strategy, **metrics, "recent_trades": trades[:50]})


@router.get("/trades")
async def trades(strategy: str | None = None, limit: int = 200, engine: TradingEngine = Depends(get_engine)):
    return ok(await engine.analytics_service.trades(strategy=strategy, limit=limit))
