from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime

from app.core.event_bus import Event, EventBus
from app.core.events import EventType

_LEVEL_BY_EVENT: dict[EventType, str] = {
    EventType.INFO_NOTIFICATION: "info",
    EventType.WARNING_NOTIFICATION: "warning",
    EventType.ERROR_NOTIFICATION: "error",
    EventType.CRITICAL_NOTIFICATION: "critical",
    EventType.RISK_REJECTED: "warning",
    EventType.DAILY_LOSS_HIT: "critical",
    EventType.MAX_EXPOSURE_HIT: "warning",
    EventType.RECOVERY_STARTED: "warning",
    EventType.RECOVERY_COMPLETED: "info",
    EventType.RECOVERY_FAILED: "critical",
    EventType.BROKER_RECONNECTED: "info",
    EventType.MARKET_DATA_RECONNECTED: "info",
    EventType.TRADE_ENTERED: "info",
    EventType.TRADE_EXITED: "info",
}

_MESSAGE_BUILDERS = {
    EventType.DAILY_LOSS_HIT: lambda p: f"Daily loss limit hit ({p.get('loss_pct', 0):.2f}%)",
    EventType.MAX_EXPOSURE_HIT: lambda p: "Portfolio exposure limit reached",
    EventType.RECOVERY_STARTED: lambda p: f"Recovery started: {p.get('component', 'unknown')}",
    EventType.RECOVERY_COMPLETED: lambda p: f"Recovery completed: {p.get('component', 'unknown')}",
    EventType.RECOVERY_FAILED: lambda p: f"Recovery failed: {p.get('component', 'unknown')}",
    EventType.BROKER_RECONNECTED: lambda p: "Broker reconnected",
    EventType.MARKET_DATA_RECONNECTED: lambda p: "Market data reconnected",
    EventType.TRADE_ENTERED: lambda p: f"{p.get('strategy')} entered {p.get('direction')} {p.get('symbol')}",
    EventType.TRADE_EXITED: lambda p: f"{p.get('strategy')} exited {p.get('symbol')} pnl={p.get('pnl')}",
}


class NotificationService:
    """Notification levels: info, warning, error, critical. Notifications
    remain until acknowledged (per DASHBOARD.md); kept in memory (not
    market/trade history) with a bounded buffer."""

    def __init__(self, event_bus: EventBus, max_size: int = 500) -> None:
        self._bus = event_bus
        self._notifications: deque[dict] = deque(maxlen=max_size)
        self._bus.subscribe_all(self._on_event)

    async def _on_event(self, event: Event) -> None:
        level = _LEVEL_BY_EVENT.get(event.event_type)
        if level is None:
            return
        builder = _MESSAGE_BUILDERS.get(event.event_type)
        message = builder(event.payload) if builder else event.payload.get("message", event.event_type.value)
        self._notifications.append(
            {
                "id": str(uuid.uuid4()),
                "level": level,
                "message": message,
                "event_type": event.event_type.value,
                "source": event.source,
                "created_at": datetime.now(UTC).isoformat(),
                "read": False,
            }
        )

    def list(self, *, unread_only: bool = False) -> list[dict]:
        items = list(self._notifications)
        if unread_only:
            items = [n for n in items if not n["read"]]
        return list(reversed(items))

    def mark_read(self, notification_id: str) -> bool:
        for notification in self._notifications:
            if notification["id"] == notification_id:
                notification["read"] = True
                return True
        return False
