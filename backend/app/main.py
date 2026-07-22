from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.websocket import register_broadcast
from app.api.websocket import router as websocket_router
from app.config import get_settings
from app.engine.trading_engine import TradingEngine
from app.schemas.common import err

logger = logging.getLogger("system")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = TradingEngine(settings)
    register_broadcast(engine.event_bus)
    app.state.engine = engine
    try:
        await engine.start()
    except Exception:
        logger.exception("engine failed to start - API will still serve, but trading is not running")
        engine.status = engine.status.__class__.STOPPED
    yield
    if engine.status.value != "stopped":
        await engine.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Trading Engine API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.dashboard_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_override(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict):
            return await http_exception_handler(request, exc)
        code = {401: "UNAUTHORIZED", 404: "NOT_FOUND", 429: "RATE_LIMITED"}.get(exc.status_code, "ERROR")
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status_code, content=err(code, str(exc.detail)))

    app.include_router(api_router)
    app.include_router(websocket_router)

    return app


app = create_app()
