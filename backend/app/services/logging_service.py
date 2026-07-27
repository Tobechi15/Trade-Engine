from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path

from app.core.event_bus import Event, EventBus
from app.core.events import PERSISTED_EVENT_TYPES, EventType
from app.db.base import SessionLocal
from app.db.models import AuditLog

LOG_CATEGORIES = ["system", "broker", "strategy", "orders", "risk", "performance", "market_data", "recovery"]

_RISK_ROUTE = {EventType.RISK_REJECTED: logging.INFO, EventType.DAILY_LOSS_HIT: logging.WARNING}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        skip = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) - {"exc_info", "stack_info"}
        for key, value in record.__dict__.items():
            if key in payload or key in skip:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        payload.pop("exc_info", None)
        payload.pop("stack_info", None)
        return json.dumps(payload, default=str)


def configure_logging(log_level: str = "INFO", log_dir: str = "logs") -> None:
    Path(log_dir).mkdir(exist_ok=True)
    formatter = JsonFormatter()

    root = logging.getLogger()
    root.setLevel(log_level)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    for category in LOG_CATEGORIES:
        logger = logging.getLogger(category)
        handler = logging.handlers.RotatingFileHandler(
            Path(log_dir) / f"{category}.log", maxBytes=10_000_000, backupCount=5
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = True


class LoggingService:
    """Persists critical events (per EVENT_BUS.md persistence rules) as
    audit log rows, and mirrors risk rejections into the risk logger with
    full context, per RISK_ENGINE.md ('every rejection is logged')."""

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._risk_logger = logging.getLogger("risk")
        self._bus.subscribe_all(self._on_event)

    async def _on_event(self, event: Event) -> None:
        if event.event_type == EventType.RISK_REJECTED:
            self._risk_logger.info(
                "signal rejected",
                extra={
                    "strategy": event.payload.get("strategy"),
                    "symbol": event.payload.get("symbol"),
                    "reason": event.payload.get("reason"),
                    "rejected_rule": event.payload.get("rejected_rule"),
                },
            )

        if event.event_type not in PERSISTED_EVENT_TYPES:
            return
        level = "CRITICAL" if event.event_type == EventType.RECOVERY_FAILED else "INFO"
        async with SessionLocal() as session:
            session.add(
                AuditLog(
                    category=_category_for(event.event_type),
                    level=level,
                    message=f"{event.event_type.value} from {event.source}",
                    strategy=event.payload.get("strategy"),
                    context=event.payload,
                )
            )
            await session.commit()


def _category_for(event_type: EventType) -> str:
    if event_type in (EventType.TRADE_ENTERED, EventType.TRADE_EXITED):
        return "performance"
    if event_type == EventType.ORDER_FILLED:
        return "orders"
    if event_type in (EventType.RISK_REJECTED, EventType.DAILY_LOSS_HIT):
        return "risk"
    if event_type in (EventType.SIGNAL_GENERATED, EventType.SIGNAL_REJECTED):
        return "strategy"
    if event_type == EventType.RECOVERY_FAILED:
        return "recovery"
    return "system"
