from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Awaitable, Callable

import httpx
import websockets
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.brokers.base import (
    BrokerAccount,
    BrokerInterface,
    BrokerOrder,
    BrokerPosition,
    FillCallback,
    OrderRequest,
)
from app.config import Settings
from app.core.bybit_symbols import from_bybit_symbol, to_bybit_symbol
from app.core.exceptions import ProviderAuthError

logger = logging.getLogger("broker")

# --------------------------------------------------------------------------
# Bybit TradFi (tokenized US stocks/ETFs) trades as USDT-settled linear
# perpetual contracts on the standard V5 API - category="linear", symbols
# like "SPYUSDT" (confirmed via Bybit's TradFi announcements and API docs,
# see backend/README.md). This adapter implements Bybit's standard V5
# request-signing scheme against that same category. Symbol translation
# (plain ticker <-> "{TICKER}USDT") happens only at this boundary - see
# app/core/bybit_symbols.py.
# --------------------------------------------------------------------------


class BybitAPIError(RuntimeError):
    def __init__(self, ret_code: int, ret_msg: str) -> None:
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        super().__init__(f"Bybit API error {ret_code}: {ret_msg}")


class BybitTradFiBroker(BrokerInterface):
    CATEGORY = "linear"
    ORDER_CREATE_PATH = "/v5/order/create"
    ORDER_CANCEL_PATH = "/v5/order/cancel"
    ORDER_AMEND_PATH = "/v5/order/amend"
    OPEN_ORDERS_PATH = "/v5/order/realtime"
    POSITIONS_PATH = "/v5/position/list"
    WALLET_BALANCE_PATH = "/v5/account/wallet-balance"
    INSTRUMENTS_PATH = "/v5/market/instruments-info"

    # Filters instruments-info down to stocks/ETFs (excludes crypto perps,
    # forex, metals, commodities also listed under category="linear").
    # IMPORTANT: this environment's outbound requests to api.bybit.com were
    # geo-blocked, so the exact `symbolType` field values could not be
    # verified against a live response - confirm before relying on this in
    # production (see app/market_data/massive.py for the same caveat noted
    # against Massive's docs).
    TRADFI_SYMBOL_TYPES = {"stock", "etf"}

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(base_url=settings.bybit_base_url, timeout=10.0)
        self._connected = False
        self._ws_task = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _require_credentials(self) -> None:
        # A known, deterministic case worth short-circuiting rather than
        # guessing at Bybit's response shape for missing credentials: no
        # key/secret configured at all means auth will never succeed until
        # they're set, so fail fast without even a network round-trip -
        # RecoveryService backs off this class of error much longer than
        # an ordinary dropped connection (ProviderAuthError).
        if not self._settings.bybit_api_key or not self._settings.bybit_api_secret:
            raise ProviderAuthError("BYBIT_API_KEY / BYBIT_API_SECRET not configured")

    async def connect(self) -> None:
        self._require_credentials()
        # Validate credentials with a lightweight authenticated call.
        await self.get_account()
        self._connected = True
        logger.info("bybit_tradfi connected env=%s", self._settings.bybit_env)

    async def disconnect(self) -> None:
        self._connected = False
        await self._client.aclose()

    def _sign(self, timestamp: str, payload: str) -> str:
        recv_window = str(self._settings.bybit_recv_window)
        prehash = f"{timestamp}{self._settings.bybit_api_key}{recv_window}{payload}"
        return hmac.new(
            self._settings.bybit_api_secret.encode(), prehash.encode(), hashlib.sha256
        ).hexdigest()

    def _headers(self, timestamp: str, signature: str) -> dict[str, str]:
        return {
            "X-BAPI-API-KEY": self._settings.bybit_api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": str(self._settings.bybit_recv_window),
            "Content-Type": "application/json",
        }

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        timestamp = str(int(time.time() * 1000))
        if method == "GET":
            query = "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
            signature = self._sign(timestamp, query)
            response = await self._client.get(path, params=params, headers=self._headers(timestamp, signature))
        else:
            payload = json.dumps(body or {}, separators=(",", ":"))
            signature = self._sign(timestamp, payload)
            response = await self._client.post(path, content=payload, headers=self._headers(timestamp, signature))
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") not in (0, None):
            raise BybitAPIError(data.get("retCode"), data.get("retMsg", "unknown error"))
        return data.get("result", {})

    async def place_order(self, request: OrderRequest) -> BrokerOrder:
        body = {
            "category": self.CATEGORY,
            "symbol": to_bybit_symbol(request.symbol),
            "side": "Buy" if request.side == "buy" else "Sell",
            "orderType": "Market" if request.order_type == "market" else "Limit",
            "qty": str(request.quantity),
        }
        if request.order_type == "limit" and request.limit_price is not None:
            body["price"] = str(request.limit_price)
        if request.client_order_id:
            body["orderLinkId"] = request.client_order_id
        if request.stop_price is not None:
            body["stopLoss"] = str(request.stop_price)
        if request.take_profit_price is not None:
            body["takeProfit"] = str(request.take_profit_price)

        result = await self._request("POST", self.ORDER_CREATE_PATH, body=body)
        return BrokerOrder(
            broker_order_id=result.get("orderId", ""),
            client_order_id=result.get("orderLinkId"),
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled_quantity=0.0,
            status="submitted",
        )

    async def cancel_order(self, broker_order_id: str) -> None:
        await self._request(
            "POST", self.ORDER_CANCEL_PATH, body={"category": self.CATEGORY, "orderId": broker_order_id}
        )

    async def modify_order(
        self,
        broker_order_id: str,
        *,
        quantity: float | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> BrokerOrder:
        body: dict = {"category": self.CATEGORY, "orderId": broker_order_id}
        if quantity is not None:
            body["qty"] = str(quantity)
        if limit_price is not None:
            body["price"] = str(limit_price)
        if stop_price is not None:
            body["stopLoss"] = str(stop_price)
        result = await self._request("POST", self.ORDER_AMEND_PATH, body=body)
        return BrokerOrder(
            broker_order_id=broker_order_id,
            client_order_id=result.get("orderLinkId"),
            symbol=from_bybit_symbol(result.get("symbol", "")),
            side="buy" if result.get("side") == "Buy" else "sell",
            quantity=float(result.get("qty", quantity or 0.0)),
            filled_quantity=float(result.get("cumExecQty", 0.0)),
            status="submitted",
        )

    async def get_open_orders(self) -> list[BrokerOrder]:
        result = await self._request("GET", self.OPEN_ORDERS_PATH, params={"category": self.CATEGORY, "openOnly": 0})
        orders = []
        for item in result.get("list", []):
            orders.append(
                BrokerOrder(
                    broker_order_id=item.get("orderId", ""),
                    client_order_id=item.get("orderLinkId"),
                    symbol=from_bybit_symbol(item.get("symbol", "")),
                    side="buy" if item.get("side") == "Buy" else "sell",
                    quantity=float(item.get("qty", 0) or 0),
                    filled_quantity=float(item.get("cumExecQty", 0) or 0),
                    status=str(item.get("orderStatus", "")).lower(),
                    avg_fill_price=float(item.get("avgPrice", 0) or 0) or None,
                )
            )
        return orders

    async def get_tradeable_symbols(self) -> set[str]:
        symbols: set[str] = set()
        cursor = ""
        while True:
            params: dict = {"category": self.CATEGORY, "status": "Trading", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            result = await self._request("GET", self.INSTRUMENTS_PATH, params=params)
            for item in result.get("list", []):
                symbol_type = str(item.get("symbolType", "")).strip().lower()
                if symbol_type in self.TRADFI_SYMBOL_TYPES:
                    symbols.add(from_bybit_symbol(item["symbol"]))
            cursor = result.get("nextPageCursor") or ""
            if not cursor:
                break
        return symbols

    async def get_positions(self) -> list[BrokerPosition]:
        result = await self._request("GET", self.POSITIONS_PATH, params={"category": self.CATEGORY})
        positions = []
        for item in result.get("list", []):
            size = float(item.get("size", 0) or 0)
            if size == 0:
                continue
            positions.append(
                BrokerPosition(
                    symbol=from_bybit_symbol(item["symbol"]),
                    quantity=size,
                    side="long" if item.get("side") == "Buy" else "short",
                    avg_entry_price=float(item.get("avgPrice", 0) or 0),
                    unrealized_pnl=float(item.get("unrealisedPnl", 0) or 0),
                )
            )
        return positions

    async def get_account(self) -> BrokerAccount:
        result = await self._request("GET", self.WALLET_BALANCE_PATH, params={"accountType": "UNIFIED"})
        accounts = result.get("list", [{}])
        acct = accounts[0] if accounts else {}
        return BrokerAccount(
            equity=float(acct.get("totalEquity", 0) or 0),
            buying_power=float(acct.get("totalAvailableBalance", 0) or 0),
            cash=float(acct.get("totalWalletBalance", 0) or 0),
            margin_used=float(acct.get("totalMarginBalance", 0) or 0),
        )

    async def get_balances(self) -> dict[str, float]:
        account = await self.get_account()
        return {"cash": account.cash, "equity": account.equity}

    async def stream_fills(self, on_fill: FillCallback) -> None:
        self._require_credentials()
        timestamp = str(int((time.time() + 1) * 1000))
        signature = hmac.new(
            self._settings.bybit_api_secret.encode(),
            f"GET/realtime{timestamp}".encode(),
            hashlib.sha256,
        ).hexdigest()
        auth_payload = {
            "op": "auth",
            "args": [self._settings.bybit_api_key, timestamp, signature],
        }
        # Reconnection timing (exponential backoff) is owned by the Recovery
        # Service, which supervises this coroutine as a restartable task.
        # This method itself just runs one connection attempt and raises on
        # disconnect so the supervisor can decide when to retry.
        ping_task: asyncio.Task | None = None
        try:
            async with websockets.connect(self._settings.bybit_ws_url, ping_interval=None) as ws:
                await ws.send(json.dumps(auth_payload))
                auth_response = json.loads(await ws.recv())
                if not auth_response.get("success", False):
                    raise BybitAPIError(
                        auth_response.get("ret_code", -1), auth_response.get("ret_msg", "authentication failed")
                    )

                await ws.send(json.dumps({"op": "subscribe", "args": ["order"]}))
                subscribe_response = json.loads(await ws.recv())
                if not subscribe_response.get("success", False):
                    raise BybitAPIError(
                        subscribe_response.get("ret_code", -1), subscribe_response.get("ret_msg", "subscribe failed")
                    )

                ping_task = asyncio.create_task(self._keep_alive(ws))
                async for raw in ws:
                    message = json.loads(raw)
                    for entry in message.get("data", []):
                        await on_fill(
                            BrokerOrder(
                                broker_order_id=entry.get("orderId", ""),
                                client_order_id=entry.get("orderLinkId"),
                                symbol=from_bybit_symbol(entry.get("symbol", "")),
                                side="buy" if entry.get("side") == "Buy" else "sell",
                                quantity=float(entry.get("qty", 0) or 0),
                                filled_quantity=float(entry.get("cumExecQty", 0) or 0),
                                status=str(entry.get("orderStatus", "")).lower(),
                                avg_fill_price=float(entry.get("avgPrice", 0) or 0) or None,
                            )
                        )
        except (websockets.ConnectionClosed, OSError) as exc:
            logger.warning("bybit_tradfi fill stream disconnected: %s", exc)
            self._connected = False
            raise
        finally:
            if ping_task:
                ping_task.cancel()

    async def _keep_alive(self, ws: websockets.WebSocketClientProtocol) -> None:
        # Bybit's V5 WS expects an application-level ping (not just a
        # protocol frame) at least every 20s or it drops the connection.
        while True:
            await asyncio.sleep(20)
            await ws.send(json.dumps({"op": "ping"}))
