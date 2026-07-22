from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    auth,
    engine,
    health,
    logs,
    notifications,
    orders,
    portfolio,
    positions,
    recovery,
    risk,
    scanner,
    settings,
    strategies,
)

api_router = APIRouter()
for module in (
    auth, health, engine, strategies, scanner, orders, positions,
    portfolio, risk, analytics, logs, notifications, recovery, settings,
):
    api_router.include_router(module.router)
