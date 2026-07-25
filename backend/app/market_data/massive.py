from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
import websockets
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.core.exceptions import ProviderAuthError
from app.market_data.base import Bar, BarCallback, MarketDataInterface, QuoteCallback, QuoteTick

logger = logging.getLogger("market_data")

# Massive (formerly Polygon.io, rebranded 2025-10-30 - see
# https://massive.com/blog/polygon-is-now-massive) is used for market data
# only; Bybit remains execution-only. Confirmed against massive.com/docs
# and the official massive-com/client-python source:
#   - REST base: https://api.massive.com (api.polygon.io still works too)
#   - Auth: `Authorization: Bearer <API_KEY>` header
#   - Aggregates: GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
#   - Full market snapshot (for ranking by activity): GET /v2/snapshot/locale/us/markets/stocks/tickers
#   - Indices tickers use an "I:" prefix, e.g. "I:VIX" (confirmed)
#
# NOT independently verified (this environment's outbound requests to
# massive.com/polygon.io endpoints were geo-blocked, so these are the
# best-documented values from Massive's docs/client, not a live-tested
# response) - confirm before relying on them in production:
#   - WS host: wss://socket.massive.com/stocks (inferred from the
#     api.polygon.io -> api.massive.com rename pattern; polygon.io's
#     legacy wss://socket.polygon.io/stocks is the documented fallback)
#   - NYSE $ADD (advance-decline breadth) ticker/availability - unconfirmed
#     whether Massive carries this at all. get_index_value() returns None
#     if the request fails, and callers must treat that as "no data",
#     never fabricate a value.
_TIMEFRAME_TO_AGGS = {
    "1Min": (1, "minute"),
    "5Min": (5, "minute"),
    "15Min": (15, "minute"),
    "1Hour": (1, "hour"),
    "1Day": (1, "day"),
}


class MassiveMarketData(MarketDataInterface):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.massive_base_url,
            headers={"Authorization": f"Bearer {settings.massive_api_key}"},
            timeout=15.0,
        )
        self._connected = False
        self._subscribed_symbols: list[str] = []
        self._ws: websockets.WebSocketClientProtocol | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        response = await self._client.get("/v3/reference/tickers", params={"limit": 1})
        response.raise_for_status()
        self._connected = True
        logger.info("massive market data connected")

    async def disconnect(self) -> None:
        self._connected = False
        if self._ws is not None:
            await self._ws.close()
        await self._client.aclose()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def get_historical_bars(
        self, symbols: list[str], start: datetime, end: datetime, timeframe: str = "1Min"
    ) -> dict[str, list[Bar]]:
        multiplier, timespan = _TIMEFRAME_TO_AGGS.get(timeframe, (1, "minute"))
        from_str = start.astimezone(UTC).date().isoformat()
        to_str = end.astimezone(UTC).date().isoformat()
        result: dict[str, list[Bar]] = {}

        for symbol in symbols:
            bars: list[Bar] = []
            url = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_str}/{to_str}"
            params = {"adjusted": "true", "sort": "asc", "limit": 50000}
            while url:
                response = await self._client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                for row in data.get("results", []) or []:
                    bars.append(
                        Bar(
                            symbol=symbol,
                            timestamp=datetime.fromtimestamp(row["t"] / 1000, tz=UTC),
                            open=row["o"],
                            high=row["h"],
                            low=row["l"],
                            close=row["c"],
                            volume=row["v"],
                        )
                    )
                next_url = data.get("next_url")
                if not next_url:
                    break
                url = next_url
                params = {}  # next_url already carries query params (incl. cursor)

            result[symbol] = bars
        return result

    async def get_active_symbols(self, limit: int) -> list[str]:
        """Ranks the full US stocks snapshot by dollar volume (day.v *
        day.vw) and returns the top `limit` tickers, most active first.
        Falls back to the static candidate list if the snapshot endpoint
        isn't available on the current plan (confirmed: not included on
        Massive's free tier) - never raises, since ORB's universe-building
        needs *some* candidate pool to proceed with."""
        try:
            response = await self._client.get("/v2/snapshot/locale/us/markets/stocks/tickers")
            response.raise_for_status()
            tickers = response.json().get("tickers", [])

            def dollar_volume(item: dict) -> float:
                day = item.get("day") or {}
                return float(day.get("v") or 0) * float(day.get("vw") or day.get("c") or 0)

            ranked = sorted(tickers, key=dollar_volume, reverse=True)
            symbols = [t["ticker"] for t in ranked[:limit] if t.get("ticker")]
            if symbols:
                return symbols
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                logger.warning(
                    "get_active_symbols: full-market snapshot not available on the current Massive "
                    "plan (HTTP %d) - falling back to the static candidate list. Upgrade to Stocks "
                    "Starter or higher for dynamic universe discovery.",
                    exc.response.status_code,
                )
            else:
                logger.exception("get_active_symbols: snapshot request failed - falling back to static candidates")
        except Exception:
            logger.exception("get_active_symbols: unexpected failure - falling back to static candidates")

        from app.strategies.orb import DEFAULT_CANDIDATES

        return DEFAULT_CANDIDATES[:limit]

    async def get_index_value(self, index_symbol: str) -> float | None:
        """Latest close for an index ticker (e.g. "VIX" -> "I:VIX", "ADD"
        -> "I:ADD"). Returns None if unavailable - never fabricates a
        value, since some indices (e.g. NYSE breadth) may not be carried."""
        ticker = index_symbol if index_symbol.startswith("I:") else f"I:{index_symbol}"
        today = datetime.now(UTC).date()
        start = today - timedelta(days=5)
        try:
            response = await self._client.get(
                f"/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{today.isoformat()}",
                params={"sort": "desc", "limit": 1},
            )
            response.raise_for_status()
            results = response.json().get("results") or []
            if not results:
                return None
            return float(results[0]["c"])
        except (httpx.HTTPStatusError, httpx.TransportError, KeyError, ValueError):
            logger.warning("index value unavailable for %s", ticker, exc_info=True)
            return None

    async def update_subscriptions(self, symbols: list[str]) -> None:
        self._subscribed_symbols = symbols
        if self._ws is not None:
            args = ",".join(f"AM.{s}" for s in symbols) + "," + ",".join(f"Q.{s}" for s in symbols)
            await self._ws.send(json.dumps({"action": "subscribe", "params": args}))

    async def stream(self, symbols: list[str], on_bar: BarCallback, on_quote: QuoteCallback) -> None:
        self._subscribed_symbols = symbols
        args = ",".join(f"AM.{s}" for s in symbols) + "," + ",".join(f"Q.{s}" for s in symbols)
        try:
            async with websockets.connect(self._settings.massive_ws_url, ping_interval=20) as ws:
                self._ws = ws
                await ws.recv()  # "connected" status frame

                await ws.send(json.dumps({"action": "auth", "params": self._settings.massive_api_key}))
                auth_response = json.loads(await ws.recv())
                auth_status = (auth_response[0] if auth_response else {}).get("status")
                if auth_status != "auth_success":
                    # Confirmed: Massive's free tier doesn't include
                    # WebSocket streaming at all - this is where that
                    # shows up (an auth/entitlement rejection, not a
                    # transient disconnect). RecoveryService backs off far
                    # longer for ProviderAuthError than for a normal drop,
                    # since retrying every 30s will never succeed on this
                    # plan.
                    raise ProviderAuthError(
                        f"Massive WebSocket auth/entitlement rejected: {auth_response} - "
                        "confirm your plan includes WebSocket streaming (not included on the free tier)"
                    )

                await ws.send(json.dumps({"action": "subscribe", "params": args}))

                async for raw in ws:
                    for message in json.loads(raw):
                        event_type = message.get("ev")
                        if event_type == "AM":
                            await on_bar(
                                Bar(
                                    symbol=message["sym"],
                                    timestamp=datetime.fromtimestamp(message["s"] / 1000, tz=UTC),
                                    open=message["o"],
                                    high=message["h"],
                                    low=message["l"],
                                    close=message["c"],
                                    volume=message["v"],
                                )
                            )
                        elif event_type == "Q":
                            bid = message.get("bp")
                            ask = message.get("ap")
                            if bid is None or ask is None:
                                continue
                            await on_quote(
                                QuoteTick(
                                    symbol=message["sym"],
                                    bid=float(bid),
                                    ask=float(ask),
                                    timestamp=datetime.fromtimestamp(message.get("t", 0) / 1000, tz=UTC),
                                )
                            )
        except websockets.InvalidStatus as exc:
            # The server can also reject the handshake itself (before any
            # of our own auth/subscribe messages) with a plain HTTP status
            # if the plan doesn't allow a WS upgrade at all.
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in (401, 403):
                raise ProviderAuthError(
                    f"Massive WebSocket handshake rejected (HTTP {status_code}) - confirm your plan "
                    "includes WebSocket streaming (not included on the free tier)"
                ) from exc
            raise
        except (websockets.ConnectionClosed, OSError) as exc:
            logger.warning("massive market data stream disconnected: %s", exc)
            self._connected = False
            self._ws = None
            raise
