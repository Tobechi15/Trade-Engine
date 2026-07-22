from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_engine
from app.engine.trading_engine import TradingEngine
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/scanner", tags=["scanner"], dependencies=[Depends(get_current_user)])


def _row(engine: TradingEngine, symbol: str) -> dict:
    quote = engine.market_state.live_quotes.get(symbol)
    opening_range = engine.market_state.opening_ranges.get(symbol)
    profile = engine.market_state.volume_profiles.get(symbol)
    position = engine.market_state.active_positions.get(symbol)

    rvol = None
    if profile and quote:
        minute_key = quote.timestamp.strftime("%H:%M")
        avg = profile.average_cumulative_volume.get(minute_key)
        if avg:
            rvol = profile.today_cumulative_volume / avg

    status = "watching"
    if symbol in engine.market_state.qualified_symbols:
        status = "qualified"
    if position:
        status = "entered"

    return {
        "symbol": symbol,
        "price": quote.price if quote else None,
        "spread_pct": ((quote.ask - quote.bid) / quote.price * 100) if quote and quote.price else None,
        "rvol": rvol,
        "opening_range": (
            {"high": opening_range.high, "low": opening_range.low, "midpoint": opening_range.midpoint}
            if opening_range
            else None
        ),
        "status": status,
    }


@router.get("")
async def scanner(engine: TradingEngine = Depends(get_engine)):
    rows = [_row(engine, symbol) for symbol in sorted(engine.market_state.universe)]
    return ok(rows)


@router.get("/qualified")
async def qualified(engine: TradingEngine = Depends(get_engine)):
    rows = [_row(engine, symbol) for symbol in sorted(engine.market_state.qualified_symbols)]
    return ok(rows)
