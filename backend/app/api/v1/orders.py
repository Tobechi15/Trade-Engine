from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import get_current_user, get_engine
from app.api.rate_limit import rate_limit
from app.db.base import SessionLocal
from app.db.models import Order
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/orders", tags=["orders"], dependencies=[Depends(get_current_user)])


def _serialize(order: Order) -> dict:
    return {
        "order_id": order.id,
        "broker_order_id": order.broker_order_id,
        "strategy": order.strategy,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "filled_quantity": order.filled_quantity,
        "entry_price": order.avg_fill_price,
        "stop_price": order.stop_price,
        "take_profit_price": order.take_profit_price,
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


@router.get("")
async def list_orders(limit: int = 200, engine: TradingEngine = Depends(get_engine)):
    async with SessionLocal() as session:
        rows = (await session.execute(select(Order).order_by(Order.created_at.desc()).limit(limit))).scalars().all()
    return ok([_serialize(r) for r in rows])


@router.get("/open")
async def open_orders(engine: TradingEngine = Depends(get_engine)):
    return ok(list(engine.market_state.active_orders.values()))


@router.get("/{order_id}")
async def get_order(order_id: str):
    async with SessionLocal() as session:
        row = (await session.execute(select(Order).where(Order.id == order_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return ok(_serialize(row))


@router.post("/{order_id}/cancel")
async def cancel_order(order_id: str, engine: TradingEngine = Depends(get_engine)):
    async with SessionLocal() as session:
        row = (await session.execute(select(Order).where(Order.id == order_id))).scalars().first()
    if row is None or row.broker_order_id is None:
        raise HTTPException(status_code=404, detail="Order not found")
    await engine.order_manager.cancel_order(row.broker_order_id)
    return ok({"order_id": order_id, "status": "cancelled"})


@router.post("/cancel-all", dependencies=[Depends(rate_limit("critical", 10))])
async def cancel_all(engine: TradingEngine = Depends(get_engine)):
    await engine.order_manager.cancel_all()
    return ok({"cancelled": True})
