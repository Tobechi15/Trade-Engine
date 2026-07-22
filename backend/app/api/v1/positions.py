from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_engine
from app.api.rate_limit import rate_limit
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/positions", tags=["positions"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_positions(engine: TradingEngine = Depends(get_engine)):
    return ok(list(engine.market_state.active_positions.values()))


@router.get("/open")
async def open_positions(engine: TradingEngine = Depends(get_engine)):
    return ok(list(engine.market_state.active_positions.values()))


@router.post("/close-all", dependencies=[Depends(rate_limit("critical", 10))])
async def close_all(engine: TradingEngine = Depends(get_engine)):
    orders = await engine.order_manager.close_all(reason="manual_close_all")
    return ok({"closed": len(orders)})


@router.post("/{symbol}/close")
async def close_position(symbol: str, engine: TradingEngine = Depends(get_engine)):
    if symbol not in engine.market_state.active_positions:
        raise HTTPException(status_code=404, detail="Position not found")
    order = await engine.order_manager.close_position(symbol, reason="manual_close")
    return ok({"symbol": symbol, "broker_order_id": order.broker_order_id if order else None})
