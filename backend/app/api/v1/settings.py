from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_user, get_engine
from app.db.base import SessionLocal
from app.db.models import UserSettings
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/settings", tags=["settings"], dependencies=[Depends(get_current_user)])

SETTINGS_KEY = "general"


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


@router.get("")
async def get_settings_endpoint(engine: TradingEngine = Depends(get_engine)):
    async with SessionLocal() as session:
        row = (await session.execute(select(UserSettings).where(UserSettings.key == SETTINGS_KEY))).scalars().first()
    stored = row.value if row else {}
    return ok(
        {
            "broker": {"environment": engine.settings.bybit_env, "paper_trading": engine.settings.bybit_env != "live"},
            "market_data": {"provider": "alpaca"},
            "strategies": engine.strategy_manager.status(),
            **stored,
        }
    )


@router.put("")
async def update_settings_endpoint(payload: SettingsUpdate):
    async with SessionLocal() as session:
        row = (await session.execute(select(UserSettings).where(UserSettings.key == SETTINGS_KEY))).scalars().first()
        if row is None:
            row = UserSettings(key=SETTINGS_KEY, value=payload.values)
            session.add(row)
        else:
            row.value = {**row.value, **payload.values}
        await session.commit()
        return ok(row.value)
