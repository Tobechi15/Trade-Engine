from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user, get_engine
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/risk", tags=["risk"], dependencies=[Depends(get_current_user)])


class RiskSettingsUpdate(BaseModel):
    risk_per_trade_pct: float | None = None
    daily_loss_limit_pct: float | None = None
    max_concurrent_positions: int | None = None
    max_portfolio_exposure_pct: float | None = None
    max_strategy_allocation_pct: float | None = None
    max_spread_pct: float | None = None
    max_slippage_pct: float | None = None


class AllocationUpdate(BaseModel):
    allocation: dict[str, float]


def _settings_dict(engine: TradingEngine) -> dict[str, Any]:
    s = engine.risk_engine.settings
    return {
        "risk_per_trade_pct": s.risk_per_trade_pct,
        "daily_loss_limit_pct": s.daily_loss_limit_pct,
        "max_concurrent_positions": s.max_concurrent_positions,
        "max_portfolio_exposure_pct": s.max_portfolio_exposure_pct,
        "max_strategy_allocation_pct": s.max_strategy_allocation_pct,
        "max_spread_pct": s.max_spread_pct,
        "max_slippage_pct": s.max_slippage_pct,
        "trading_enabled": s.trading_enabled,
    }


@router.get("")
async def get_risk(engine: TradingEngine = Depends(get_engine)):
    return ok({**_settings_dict(engine), "allocation": engine.risk_engine.settings.strategy_allocation})


@router.put("/settings")
async def update_settings(payload: RiskSettingsUpdate, engine: TradingEngine = Depends(get_engine)):
    settings = engine.risk_engine.settings
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(settings, field, value)
    await engine.risk_engine.save_settings()
    return ok(_settings_dict(engine))


@router.get("/allocation")
async def get_allocation(engine: TradingEngine = Depends(get_engine)):
    return ok(engine.risk_engine.settings.strategy_allocation)


@router.put("/allocation")
async def update_allocation(payload: AllocationUpdate, engine: TradingEngine = Depends(get_engine)):
    engine.risk_engine.settings.strategy_allocation = payload.allocation
    await engine.risk_engine.save_settings()
    return ok(engine.risk_engine.settings.strategy_allocation)


@router.get("/current")
async def current_risk(engine: TradingEngine = Depends(get_engine)):
    return ok(engine.risk_engine.status())
