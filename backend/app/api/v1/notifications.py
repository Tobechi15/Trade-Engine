from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_engine
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_notifications(unread_only: bool = False, engine: TradingEngine = Depends(get_engine)):
    return ok(engine.notification_service.list(unread_only=unread_only))


@router.post("/read/{notification_id}")
async def mark_read(notification_id: str, engine: TradingEngine = Depends(get_engine)):
    if not engine.notification_service.mark_read(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return ok({"id": notification_id, "read": True})
