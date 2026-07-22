from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_engine
from app.api.rate_limit import rate_limit
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/engine", tags=["engine"], dependencies=[Depends(get_current_user)])


@router.get("/status")
async def status(engine: TradingEngine = Depends(get_engine)):
    return ok(engine.status_payload())


@router.post("/start")
async def start(engine: TradingEngine = Depends(get_engine)):
    if engine.status.value == "stopped":
        await engine.start()
    return ok(engine.status_payload())


@router.post("/pause")
async def pause(engine: TradingEngine = Depends(get_engine)):
    await engine.pause()
    return ok(engine.status_payload())


@router.post("/resume")
async def resume(engine: TradingEngine = Depends(get_engine)):
    await engine.resume()
    return ok(engine.status_payload())


@router.post("/stop", dependencies=[Depends(rate_limit("critical", 10))])
async def stop(engine: TradingEngine = Depends(get_engine)):
    await engine.stop()
    return ok(engine.status_payload())
