from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_engine
from app.db.base import SessionLocal
from app.db.models import StrategyPerformance
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_strategies(engine: TradingEngine = Depends(get_engine)):
    return ok(engine.strategy_manager.status())


@router.get("/{strategy}")
async def get_strategy(strategy: str, engine: TradingEngine = Depends(get_engine)):
    instance = engine.strategy_manager.get(strategy)
    if instance is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return ok({"name": instance.name, "enabled": instance.enabled, "config": instance.config})


@router.post("/{strategy}/enable")
async def enable_strategy(strategy: str, engine: TradingEngine = Depends(get_engine)):
    if engine.strategy_manager.get(strategy) is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    engine.strategy_manager.enable(strategy)
    return ok({"strategy": strategy, "enabled": True})


@router.post("/{strategy}/disable")
async def disable_strategy(strategy: str, engine: TradingEngine = Depends(get_engine)):
    if engine.strategy_manager.get(strategy) is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    engine.strategy_manager.disable(strategy)
    return ok({"strategy": strategy, "enabled": False})


@router.post("/{strategy}/reload")
async def reload_strategy(strategy: str, engine: TradingEngine = Depends(get_engine)):
    if engine.strategy_manager.get(strategy) is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await engine.strategy_manager.reload(strategy)
    return ok({"strategy": strategy, "reloaded": True})


@router.get("/{strategy}/metrics")
async def strategy_metrics(strategy: str, engine: TradingEngine = Depends(get_engine)):
    if engine.strategy_manager.get(strategy) is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    async with SessionLocal() as session:
        row = (
            await session.execute(select(StrategyPerformance).where(StrategyPerformance.strategy == strategy))
        ).scalars().first()
    if row is None:
        return ok(
            {
                "strategy": strategy, "total_trades": 0, "win_rate": 0.0, "pnl": 0.0,
                "drawdown": 0.0, "expectancy": 0.0,
            }
        )
    return ok(
        {
            "strategy": strategy,
            "total_trades": row.total_trades,
            "winning_trades": row.winning_trades,
            "losing_trades": row.losing_trades,
            "win_rate": row.win_rate,
            "profit_factor": row.profit_factor,
            "sharpe_ratio": row.sharpe_ratio,
            "max_drawdown": row.max_drawdown,
            "expectancy": row.expectancy,
            "average_winner": row.average_winner,
            "average_loser": row.average_loser,
            "average_hold_time_seconds": row.average_hold_time_seconds,
        }
    )
