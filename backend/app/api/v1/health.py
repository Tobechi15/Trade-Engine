from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_engine
from app.api.websocket import manager
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.api_route("", methods=["GET", "HEAD"])
async def health(engine: TradingEngine = Depends(get_engine)):
    return ok(
        {
            "engine": engine.status.value,
            "broker": engine.recovery_service.broker_status,
            "market_data": engine.recovery_service.market_data_status,
            "database": engine.recovery_service.database_status,
            "scheduler": "running" if engine.scheduler.running else "stopped",
        }
    )


@router.get("/details")
async def health_details(engine: TradingEngine = Depends(get_engine)):
    from app.core.time_service import TimeService

    uptime = (TimeService.now_utc() - engine.started_at).total_seconds() if engine.started_at else 0
    return ok(
        {
            "uptime_seconds": uptime,
            "websocket_connections": len(manager._connections),  # noqa: SLF001
            "reconnect_counts": engine.recovery_service._reconnect_attempts,  # noqa: SLF001
            "last_market_update": (
                engine.market_state.account_snapshot.updated_at.isoformat()
                if engine.market_state.account_snapshot.updated_at
                else None
            ),
        }
    )
