from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.events import EventType

logger = logging.getLogger("system")

EventHandler = Callable[["Event"], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Event:
    event_type: EventType
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "payload": self.payload,
        }


class EventBus:
    """Async, in-memory publish/subscribe backbone.

    Ordering is guaranteed only within a single event-type stream: each
    event type has its own queue and worker task, so two different event
    types are processed concurrently but events of the same type are
    processed strictly in publish order. No service owns the bus; it just
    fans events out to whoever subscribed.
    """

    def __init__(self, history_size: int = 2000) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []
        self._queues: dict[EventType, asyncio.Queue[Event]] = {}
        self._workers: dict[EventType, asyncio.Task[None]] = {}
        self._history: deque[Event] = deque(maxlen=history_size)
        self._running = False

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)
        if self._running:
            self._ensure_worker(event_type)

    def subscribe_many(self, event_types: list[EventType], handler: EventHandler) -> None:
        for event_type in event_types:
            self.subscribe(event_type, handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Observability hook: receives every event, e.g. logging, WS fan-out."""
        self._global_handlers.append(handler)

    async def start(self) -> None:
        self._running = True
        for event_type in list(self._handlers.keys()):
            self._ensure_worker(event_type)

    async def stop(self) -> None:
        self._running = False
        for queue in self._queues.values():
            await queue.join()
        for task in self._workers.values():
            task.cancel()
        for task in self._workers.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._workers.clear()

    def _ensure_worker(self, event_type: EventType) -> None:
        if event_type in self._workers:
            return
        queue: asyncio.Queue[Event] = self._queues.setdefault(event_type, asyncio.Queue())
        self._workers[event_type] = asyncio.create_task(
            self._worker(event_type, queue), name=f"event-bus-{event_type.value}"
        )

    async def _worker(self, event_type: EventType, queue: asyncio.Queue[Event]) -> None:
        while True:
            event = await queue.get()
            try:
                for handler in list(self._handlers.get(event_type, [])) + self._global_handlers:
                    try:
                        await handler(event)
                    except Exception:
                        logger.exception(
                            "event handler failed", extra={"event_type": event_type.value, "handler": getattr(handler, "__qualname__", str(handler))}
                        )
            finally:
                queue.task_done()

    async def publish(
        self, event_type: EventType, source: str, payload: dict[str, Any] | None = None
    ) -> Event:
        event = Event(event_type=event_type, source=source, payload=payload or {})
        self._history.append(event)
        if not self._running:
            # Engine not started yet (e.g. during tests) - process inline so
            # callers don't silently lose events.
            for handler in list(self._handlers.get(event_type, [])) + self._global_handlers:
                await handler(event)
            return event
        self._ensure_worker(event_type)
        await self._queues[event_type].put(event)
        return event

    def history(self, event_type: EventType | None = None, limit: int = 100) -> list[Event]:
        items = [e for e in self._history if event_type is None or e.event_type == event_type]
        return items[-limit:]
