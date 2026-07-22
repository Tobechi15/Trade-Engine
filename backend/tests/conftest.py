import pytest

from app.core.event_bus import EventBus
from app.core.market_state import MarketState


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def market_state() -> MarketState:
    return MarketState()
