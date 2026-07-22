from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_engine
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/recovery", tags=["recovery"], dependencies=[Depends(get_current_user)])


@router.get("/status")
async def status(engine: TradingEngine = Depends(get_engine)):
    return ok(engine.recovery_service.status())


@router.get("/history")
async def history(limit: int = 50, engine: TradingEngine = Depends(get_engine)):
    return ok(engine.recovery_service.history(limit=limit))


@router.post("/reconnect")
async def reconnect(engine: TradingEngine = Depends(get_engine)):
    await engine.broker.connect()
    await engine.market_data_service.connect()
    return ok(engine.recovery_service.status())


@router.post("/rebuild-state")
async def rebuild_state(engine: TradingEngine = Depends(get_engine)):
    await engine.state_recovery_service.recover()
    return ok({"rebuilt": True})
