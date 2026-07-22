from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx
import websockets
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.market_data.base import Bar, BarCallback, MarketDataInterface, QuoteCallback, QuoteTick

logger = logging.getLogger("market_data")


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
        response = await self._client.get("/v2/stocks/meta/exchanges")
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
        result: dict[str, list[Bar]] = {symbol: [] for symbol in symbols}
        page_token: str | None = None
        while True:
            params = {
                "symbols": ",".join(symbols),
                "timeframe": timeframe,
                "start": start.astimezone(UTC).isoformat(),
                "end": end.astimezone(UTC).isoformat(),
                "limit": 10000,
                "adjustment": "raw",
                "feed": "iex",
            }
            if page_token:
                params["page_token"] = page_token
            response = await self._client.get("/v2/stocks/bars", params=params)
            response.raise_for_status()
            data = response.json()
            for symbol, bars in (data.get("bars") or {}).items():
                for raw in bars:
                    result.setdefault(symbol, []).append(
                        Bar(
                            symbol=symbol,
                            timestamp=datetime.fromisoformat(raw["t"].replace("Z", "+00:00")),
                            open=raw["o"],
                            high=raw["h"],
                            low=raw["l"],
                            close=raw["c"],
                            volume=raw["v"],
                        )
                    )
            page_token = data.get("next_page_token")
            if not page_token:
                break
        return result

    async def update_subscriptions(self, symbols: list[str]) -> None:
        self._subscribed_symbols = symbols
        if self._ws is not None:
            await self._ws.send(
                json.dumps({"action": "subscribe", "bars": symbols, "quotes": symbols})
            )

    async def stream(self, symbols: list[str], on_bar: BarCallback, on_quote: QuoteCallback) -> None:
        self._subscribed_symbols = symbols
        try:
            async with websockets.connect(self._settings.alpaca_stream_url, ping_interval=20) as ws:
                self._ws = ws
                await ws.recv()  # connection ack
                await ws.send(
                    json.dumps(
                        {
                            "action": "auth",
                            "key": self._settings.alpaca_api_key,
                            "secret": self._settings.alpaca_api_secret,
                        }
                    )
                )
                await ws.recv()  # auth ack
                await ws.send(json.dumps({"action": "subscribe", "bars": symbols, "quotes": symbols}))

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
                            await on_quote(
                                QuoteTick(
                                    symbol=message["S"],
                                    bid=message["bp"],
                                    ask=message["ap"],
                                    timestamp=datetime.fromisoformat(message["t"].replace("Z", "+00:00")),
                                )
                            )
        except (websockets.ConnectionClosed, OSError) as exc:
            logger.warning("alpaca market data stream disconnected: %s", exc)
            self._connected = False
            self._ws = None
            raise
