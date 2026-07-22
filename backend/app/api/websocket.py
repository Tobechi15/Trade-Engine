from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.jwt import decode_access_token
from app.config import get_settings
from app.core.event_bus import Event, EventBus
from app.core.events import EVENT_TO_CHANNELS, WEBSOCKET_CHANNELS

logger = logging.getLogger("system")
router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[websocket] = set(WEBSOCKET_CHANNELS)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    def set_channels(self, websocket: WebSocket, channels: list[str]) -> None:
        valid = {c for c in channels if c in WEBSOCKET_CHANNELS}
        self._connections[websocket] = valid or set(WEBSOCKET_CHANNELS)

    async def broadcast(self, channel: str, message: dict) -> None:
        dead = []
        for websocket, channels in self._connections.items():
            if channel not in channels:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)


manager = ConnectionManager()


def register_broadcast(event_bus: EventBus) -> None:
    async def _handler(event: Event) -> None:
        channels = EVENT_TO_CHANNELS.get(event.event_type, ())
        message = {"channel": channels[0] if channels else "engine", "payload": event.to_dict()}
        for channel in channels:
            await manager.broadcast(channel, {"channel": channel, "payload": event.to_dict()})

    event_bus.subscribe_all(_handler)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    settings = get_settings()
    if not token:
        await websocket.close(code=4401)
        return
    try:
        decode_access_token(settings, token)
    except ValueError:
        await websocket.close(code=4401)
        return

    await manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("action") == "subscribe" and isinstance(message.get("channels"), list):
                manager.set_channels(websocket, message["channels"])
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("websocket error")
        manager.disconnect(websocket)
