import pytest

from app.core.event_bus import EventBus
from app.core.events import EventType


@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber(event_bus: EventBus):
    received = []

    async def handler(event):
        received.append(event)

    event_bus.subscribe(EventType.NEW_CANDLE, handler)
    await event_bus.publish(EventType.NEW_CANDLE, source="test", payload={"symbol": "AAPL"})

    assert len(received) == 1
    assert received[0].payload["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_subscribe_all_receives_every_event(event_bus: EventBus):
    received = []

    async def handler(event):
        received.append(event.event_type)

    event_bus.subscribe_all(handler)

    await event_bus.publish(EventType.MARKET_OPEN, source="test")
    await event_bus.publish(EventType.MARKET_CLOSE, source="test")

    assert received == [EventType.MARKET_OPEN, EventType.MARKET_CLOSE]


@pytest.mark.asyncio
async def test_ordering_within_single_stream(event_bus: EventBus):
    order = []

    async def handler(event):
        order.append(event.payload["seq"])

    event_bus.subscribe(EventType.NEW_QUOTE, handler)
    await event_bus.start()
    for i in range(20):
        await event_bus.publish(EventType.NEW_QUOTE, source="test", payload={"seq": i})
    await event_bus.stop()

    assert order == list(range(20))
