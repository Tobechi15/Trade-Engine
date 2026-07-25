from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx
import websockets
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.core.exceptions import ProviderAuthError
from app.market_data.base import Bar, BarCallback, MarketDataInterface, QuoteCallback, QuoteTick

logger = logging.getLogger("market_data")

# Alpaca Market Data API. Confirmed against docs.alpaca.markets (Historical
# API / stock bars reference, streaming market data guide, plan comparison
# on "about-market-data-api"):
#   - REST base: https://data.alpaca.markets
#   - Auth: `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY` headers
#   - Multi-symbol bars: GET /v2/stocks/bars?symbols=A,B&timeframe=1Min&feed=...
#     -> {"bars": {"SYM": [{"t","o","h","l","c","v",...}]}, "next_page_token": ...}
#     (paginate via `page_token` until next_page_token is null)
#   - WS: wss://stream.data.alpaca.markets/v2/{feed} (feed = iex | sip | delayed_sip)
#     auth: {"action":"auth","key":...,"secret":...} -> [{"T":"success","msg":"authenticated"}]
#     subscribe: {"action":"subscribe","quotes":[...],"bars":[...]}
#     bar message: {"T":"b","S":sym,"t":RFC3339,"o","h","l","c","v"}
#     quote message: {"T":"q","S":sym,"t":RFC3339,"bp","ap",...}
#
# Plan limitations (Basic/free tier, confirmed via "about-market-data-api"):
#   - Real-time coverage is IEX only (not the full consolidated tape) -
#     `feed=sip` requires the paid Algo Trader Plus plan and will be
#     rejected. This adapter defaults to `settings.alpaca_feed` ("iex").
#   - WebSocket subscriptions are capped at 30 symbols on Basic.
#   - Historical bars: the most recent 15 minutes are restricted on Basic
#     (data since 2016 is otherwise available).
#   - REST rate limit: 200 req/min on Basic vs 10,000 req/min on Algo
#     Trader Plus.
#
# NOT independently verified (outbound requests to alpaca.markets were
# geo-blocked in this environment, so these are the best-documented values,
# not a live-tested response) - confirm before relying on them in
# production:
#   - The most-actives screener response shape (`most_actives` key) used by
#     get_active_symbols().
#   - Whether Alpaca carries macro indices (e.g. VIX, NYSE $ADD breadth) at
#     all via the stocks API - get_index_value() returns None rather than
#     guess, since callers must treat "no data" as "condition not met", not
#     "condition satisfied" (see app/strategies/breadth_pullback.py).
#
# Confirmed live in production (2026-07-25): code 406 ("connection limit
# exceeded") is NOT an entitlement problem - it means this same API key
# already has another WebSocket connection open elsewhere (Basic/free plan
# allows exactly one at a time). It's usually transient - a stale
# connection from a previous deploy/process that hasn't timed out yet, or
# a second client using the same key - and clears on its own. Unlike a bad
# key or a plan/feed mismatch, retrying soon can succeed, so it must NOT
# get the hour-long ProviderAuthError backoff; only codes that genuinely
# won't resolve without a human (bad credentials, insufficient
# subscription for the requested feed) do.
_ALLOWED_TIMEFRAMES = {"1Min", "5Min", "15Min", "1Hour", "1Day"}
_AUTH_REJECT_CODES = {402, 403, 404, 405, 409}


class AlpacaMarketData(MarketDataInterface):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.alpaca_data_base_url,
            headers={
                "APCA-API-KEY-ID": settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
            },
            timeout=15.0,
        )
        self._connected = False
        self._subscribed_symbols: list[str] = []
        self._ws: websockets.WebSocketClientProtocol | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        response = await self._client.get(
            "/v2/stocks/bars",
            params={"symbols": "SPY", "timeframe": "1Day", "limit": 1, "feed": self._settings.alpaca_feed},
        )
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"Alpaca REST auth rejected (HTTP {response.status_code}): {response.text} - "
                "confirm APCA-API-KEY-ID / APCA-API-SECRET-KEY are correct"
            )
        response.raise_for_status()
        self._connected = True
        logger.info("alpaca market data connected")

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
        alpaca_timeframe = timeframe if timeframe in _ALLOWED_TIMEFRAMES else "1Min"
        result: dict[str, list[Bar]] = {symbol: [] for symbol in symbols}
        params = {
            "symbols": ",".join(symbols),
            "timeframe": alpaca_timeframe,
            "start": start.astimezone(UTC).isoformat(),
            "end": end.astimezone(UTC).isoformat(),
            "limit": 10000,
            "adjustment": "raw",
            "feed": self._settings.alpaca_feed,
            "sort": "asc",
        }

        page_token: str | None = None
        while True:
            if page_token:
                params["page_token"] = page_token
            response = await self._client.get("/v2/stocks/bars", params=params)
            response.raise_for_status()
            data = response.json()
            for symbol, rows in (data.get("bars") or {}).items():
                for row in rows:
                    result.setdefault(symbol, []).append(
                        Bar(
                            symbol=symbol,
                            timestamp=datetime.fromisoformat(row["t"].replace("Z", "+00:00")),
                            open=row["o"],
                            high=row["h"],
                            low=row["l"],
                            close=row["c"],
                            volume=row["v"],
                        )
                    )
            page_token = data.get("next_page_token")
            if not page_token:
                break

        return result

    async def get_active_symbols(self, limit: int) -> list[str]:
        """Ranks symbols via Alpaca's most-actives screener. Falls back to
        the static candidate list if the screener isn't available on the
        current plan or the request fails - never raises, since ORB's
        universe-building needs *some* candidate pool to proceed with."""
        try:
            response = await self._client.get(
                "/v1beta1/screener/stocks/most-actives", params={"by": "volume", "top": limit}
            )
            response.raise_for_status()
            entries = response.json().get("most_actives", [])
            symbols = [e["symbol"] for e in entries[:limit] if e.get("symbol")]
            if symbols:
                return symbols
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                logger.warning(
                    "get_active_symbols: most-actives screener not available on the current Alpaca "
                    "plan (HTTP %d) - falling back to the static candidate list.",
                    exc.response.status_code,
                )
            else:
                logger.exception("get_active_symbols: screener request failed - falling back to static candidates")
        except Exception:
            logger.exception("get_active_symbols: unexpected failure - falling back to static candidates")

        from app.strategies.orb import DEFAULT_CANDIDATES

        return DEFAULT_CANDIDATES[:limit]

    async def get_index_value(self, index_symbol: str) -> float | None:
        """Alpaca's stocks API doesn't carry macro indices (e.g. VIX, NYSE
        $ADD breadth) - always returns None. Never fabricates a value;
        callers must treat None as missing data, not "condition met"."""
        return None

    async def update_subscriptions(self, symbols: list[str]) -> None:
        if self._ws is None:
            self._subscribed_symbols = symbols
            return

        new_set, old_set = set(symbols), set(self._subscribed_symbols)
        to_add = sorted(new_set - old_set)
        to_remove = sorted(old_set - new_set)
        if to_remove:
            await self._ws.send(json.dumps({"action": "unsubscribe", "quotes": to_remove, "bars": to_remove}))
        if to_add:
            await self._ws.send(json.dumps({"action": "subscribe", "quotes": to_add, "bars": to_add}))
        self._subscribed_symbols = symbols

    async def stream(self, symbols: list[str], on_bar: BarCallback, on_quote: QuoteCallback) -> None:
        self._subscribed_symbols = symbols
        ws_url = f"{self._settings.alpaca_stream_base_url}/{self._settings.alpaca_feed}"
        try:
            async with websockets.connect(ws_url, ping_interval=20) as ws:
                self._ws = ws
                await ws.recv()  # [{"T":"success","msg":"connected"}]

                await ws.send(
                    json.dumps(
                        {
                            "action": "auth",
                            "key": self._settings.alpaca_api_key,
                            "secret": self._settings.alpaca_api_secret,
                        }
                    )
                )
                auth_response = json.loads(await ws.recv())
                auth_frame = auth_response[0] if auth_response else {}
                if auth_frame.get("T") != "success" or auth_frame.get("msg") != "authenticated":
                    code = auth_frame.get("code")
                    if code in _AUTH_REJECT_CODES:
                        # Confirmed: Alpaca's Basic/free plan only entitles
                        # the "iex" feed - requesting "sip" here is where
                        # that rejection shows up (an auth/entitlement
                        # error, not a transient disconnect). RecoveryService
                        # backs off far longer for ProviderAuthError than
                        # for a normal drop, since retrying every 30s will
                        # never succeed on this plan/feed combination.
                        raise ProviderAuthError(
                            f"Alpaca WebSocket auth/entitlement rejected: {auth_response} - "
                            f"confirm your plan includes the '{self._settings.alpaca_feed}' feed"
                        )
                    # Anything else (e.g. code 406 "connection limit
                    # exceeded" - a stale connection elsewhere on the same
                    # key, not a credentials/plan problem) is treated as an
                    # ordinary transient failure so RecoveryService retries
                    # on the fast schedule instead of backing off an hour.
                    raise RuntimeError(f"Alpaca WebSocket auth rejected (non-entitlement): {auth_response}")

                await ws.send(json.dumps({"action": "subscribe", "quotes": symbols, "bars": symbols}))

                async for raw in ws:
                    for message in json.loads(raw):
                        msg_type = message.get("T")
                        if msg_type == "b":
                            await on_bar(
                                Bar(
                                    symbol=message["S"],
                                    timestamp=datetime.fromisoformat(message["t"].replace("Z", "+00:00")),
                                    open=message["o"],
                                    high=message["h"],
                                    low=message["l"],
                                    close=message["c"],
                                    volume=message["v"],
                                )
                            )
                        elif msg_type == "q":
                            bid = message.get("bp")
                            ask = message.get("ap")
                            if not bid or not ask:
                                continue
                            await on_quote(
                                QuoteTick(
                                    symbol=message["S"],
                                    bid=float(bid),
                                    ask=float(ask),
                                    timestamp=datetime.fromisoformat(message["t"].replace("Z", "+00:00")),
                                )
                            )
                        elif msg_type == "error":
                            code = message.get("code")
                            if code in _AUTH_REJECT_CODES:
                                raise ProviderAuthError(f"Alpaca WebSocket rejected subscription: {message}")
                            logger.warning("alpaca market data stream error frame: %s", message)
        except websockets.InvalidStatus as exc:
            # The server can also reject the handshake itself (before any
            # of our own auth/subscribe messages) with a plain HTTP status.
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in (401, 403):
                raise ProviderAuthError(
                    f"Alpaca WebSocket handshake rejected (HTTP {status_code}) - confirm your API key/secret "
                    "and that your plan includes streaming"
                ) from exc
            raise
        except (websockets.ConnectionClosed, OSError) as exc:
            logger.warning("alpaca market data stream disconnected: %s", exc)
            self._connected = False
            self._ws = None
            raise
