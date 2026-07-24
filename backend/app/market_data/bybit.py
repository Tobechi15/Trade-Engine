from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import httpx
import websockets
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.core.bybit_symbols import from_bybit_symbol, to_bybit_symbol
from app.market_data.base import Bar, BarCallback, MarketDataInterface, QuoteCallback, QuoteTick

logger = logging.getLogger("market_data")

# Bybit TradFi (US stocks/ETFs) trades as USDT-settled linear perpetuals on
# the same V5 API used for crypto - category="linear", symbols like
# "SPYUSDT". Public market data (klines, tickers) is the same feed
# regardless of demo vs live account, so it's fetched from Bybit's public
# endpoints/stream rather than the demo/live-specific trading base URL.
CATEGORY = "linear"

_TIMEFRAME_TO_INTERVAL = {
    "1Min": "1",
    "3Min": "3",
    "5Min": "5",
    "15Min": "15",
    "30Min": "30",
    "1Hour": "60",
    "1Day": "D",
}

# Bybit TradFi now lists 300+ instruments (stocks, ETFs, forex, metals,
# commodities, indices) - all still under category="linear" alongside
# crypto perpetuals. get_active_symbols() below distinguishes them via the
# instruments-info endpoint's `symbolType` field, filtered to "stock"/"etf"
# and ranked by 24h turnover from the tickers endpoint.
#
# IMPORTANT: this environment's outbound requests to api.bybit.com are
# geo-blocked (CloudFront 403), so the exact `symbolType` values below could
# not be verified against a live response - they're the best-documented
# values found (Bybit API docs + third-party integration guides). Before
# relying on this in production, run:
#   GET {base_url}/v5/market/instruments-info?category=linear&limit=50
# from a machine that isn't blocked, and confirm `symbolType` actually
# takes these values for known stock symbols like AAPLUSDT. If it doesn't
# match, update _TRADFI_SYMBOL_TYPES accordingly. If the filter ever
# matches nothing, get_active_symbols() falls back to
# app/strategies/orb.py: DEFAULT_CANDIDATES rather than returning an empty
# universe silently.
_TRADFI_SYMBOL_TYPES = {"stock", "etf"}


class BybitMarketData(MarketDataInterface):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(base_url=settings.bybit_base_url, timeout=15.0)
        self._connected = False
        self._subscribed_symbols: list[str] = []
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ping_task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        response = await self._client.get(f"/v5/market/instruments-info?category={CATEGORY}&limit=1")
        response.raise_for_status()
        self._connected = True
        logger.info("bybit market data connected")

    async def disconnect(self) -> None:
        self._connected = False
        if self._ping_task:
            self._ping_task.cancel()
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
        interval = _TIMEFRAME_TO_INTERVAL.get(timeframe, "1")
        start_ms = int(start.astimezone(UTC).timestamp() * 1000)
        end_ms = int(end.astimezone(UTC).timestamp() * 1000)
        result: dict[str, list[Bar]] = {}

        for symbol in symbols:
            bybit_symbol = to_bybit_symbol(symbol)
            bars: list[Bar] = []
            cursor_end = end_ms
            while True:
                response = await self._client.get(
                    "/v5/market/kline",
                    params={
                        "category": CATEGORY,
                        "symbol": bybit_symbol,
                        "interval": interval,
                        "start": start_ms,
                        "end": cursor_end,
                        "limit": 1000,
                    },
                )
                response.raise_for_status()
                data = response.json()
                rows = (data.get("result") or {}).get("list") or []
                if not rows:
                    break
                for row in rows:
                    ts_ms, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
                    bars.append(
                        Bar(
                            symbol=symbol,
                            timestamp=datetime.fromtimestamp(int(ts_ms) / 1000, tz=UTC),
                            open=float(o),
                            high=float(h),
                            low=float(l),
                            close=float(c),
                            volume=float(v),
                        )
                    )
                oldest_ts = int(rows[-1][0])
                if len(rows) < 1000 or oldest_ts <= start_ms:
                    break
                cursor_end = oldest_ts - 1

            bars.sort(key=lambda b: b.timestamp)
            result[symbol] = bars
        return result

    async def update_subscriptions(self, symbols: list[str]) -> None:
        self._subscribed_symbols = symbols
        if self._ws is not None:
            args = [f"kline.1.{to_bybit_symbol(s)}" for s in symbols] + [f"tickers.{to_bybit_symbol(s)}" for s in symbols]
            await self._ws.send(json.dumps({"op": "subscribe", "args": args}))

    async def _fetch_tradfi_instruments(self) -> set[str]:
        """Paginates instruments-info and returns the set of Bybit symbols
        (e.g. "AAPLUSDT") whose symbolType marks them as TradFi stocks/ETFs,
        excluding crypto perpetuals, forex, metals, and commodities."""
        symbols: set[str] = set()
        cursor = ""
        while True:
            params = {"category": CATEGORY, "status": "Trading", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            response = await self._client.get("/v5/market/instruments-info", params=params)
            response.raise_for_status()
            data = response.json()
            result = data.get("result") or {}
            for item in result.get("list", []):
                symbol_type = str(item.get("symbolType", "")).strip().lower()
                if symbol_type in _TRADFI_SYMBOL_TYPES:
                    symbols.add(item["symbol"])
            cursor = result.get("nextPageCursor") or ""
            if not cursor:
                break
        return symbols

    async def get_active_symbols(self, limit: int) -> list[str]:
        try:
            tradfi_symbols = await self._fetch_tradfi_instruments()
            if not tradfi_symbols:
                raise ValueError("no instruments matched the TradFi symbolType filter")

            response = await self._client.get("/v5/market/tickers", params={"category": CATEGORY})
            response.raise_for_status()
            tickers = (response.json().get("result") or {}).get("list", [])

            ranked = sorted(
                (t for t in tickers if t.get("symbol") in tradfi_symbols),
                key=lambda t: float(t.get("turnover24h", 0) or 0),
                reverse=True,
            )
            symbols = [from_bybit_symbol(t["symbol"]) for t in ranked[:limit]]
            if symbols:
                return symbols
            raise ValueError("no TradFi symbols had ticker data")
        except Exception:
            logger.exception(
                "get_active_symbols: dynamic TradFi symbol discovery failed, "
                "falling back to the static candidate list"
            )
            from app.strategies.orb import DEFAULT_CANDIDATES

            return DEFAULT_CANDIDATES[:limit]

    async def _keep_alive(self, ws: websockets.WebSocketClientProtocol) -> None:
        # Bybit's V5 WS expects an application-level ping (not just a
        # protocol frame) at least every 20s or it drops the connection.
        while True:
            await asyncio.sleep(20)
            await ws.send(json.dumps({"op": "ping"}))

    async def stream(self, symbols: list[str], on_bar: BarCallback, on_quote: QuoteCallback) -> None:
        self._subscribed_symbols = symbols
        args = [f"kline.1.{to_bybit_symbol(s)}" for s in symbols] + [f"tickers.{to_bybit_symbol(s)}" for s in symbols]
        try:
            async with websockets.connect(self._settings.bybit_public_ws_url, ping_interval=None) as ws:
                self._ws = ws
                self._ping_task = asyncio.create_task(self._keep_alive(ws))
                await ws.send(json.dumps({"op": "subscribe", "args": args}))

                async for raw in ws:
                    message = json.loads(raw)
                    topic = message.get("topic", "")
                    if topic.startswith("kline."):
                        await self._handle_kline(topic, message, on_bar)
                    elif topic.startswith("tickers."):
                        await self._handle_ticker(topic, message, on_quote)
        except (websockets.ConnectionClosed, OSError) as exc:
            logger.warning("bybit market data stream disconnected: %s", exc)
            self._connected = False
            self._ws = None
            raise
        finally:
            if self._ping_task:
                self._ping_task.cancel()

    async def _handle_kline(self, topic: str, message: dict, on_bar: BarCallback) -> None:
        bybit_symbol = topic.split(".")[-1]
        symbol = from_bybit_symbol(bybit_symbol)
        for entry in message.get("data", []):
            if not entry.get("confirm"):
                continue  # only emit completed candles, matching NEW_CANDLE semantics
            await on_bar(
                Bar(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(int(entry["start"]) / 1000, tz=UTC),
                    open=float(entry["open"]),
                    high=float(entry["high"]),
                    low=float(entry["low"]),
                    close=float(entry["close"]),
                    volume=float(entry["volume"]),
                )
            )

    async def _handle_ticker(self, topic: str, message: dict, on_quote: QuoteCallback) -> None:
        bybit_symbol = topic.split(".")[-1]
        symbol = from_bybit_symbol(bybit_symbol)
        data = message.get("data", {})
        bid = data.get("bid1Price")
        ask = data.get("ask1Price")
        if bid is None or ask is None:
            return
        await on_quote(
            QuoteTick(
                symbol=symbol,
                bid=float(bid),
                ask=float(ask),
                timestamp=datetime.fromtimestamp(int(message.get("ts", 0)) / 1000, tz=UTC),
            )
        )
