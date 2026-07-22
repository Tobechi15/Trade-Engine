import pytest

from app.core.event_bus import EventBus
from app.core.market_calendar import MarketCalendarService
from app.core.market_state import MarketState
from app.services.risk_engine import RiskEngine


@pytest.fixture(autouse=True)
def _market_always_open(monkeypatch):
    # Risk pipeline checks market hours; pin it open so tests are
    # deterministic regardless of when they actually run.
    monkeypatch.setattr(MarketCalendarService, "is_open", lambda self, *a, **k: True)


@pytest.fixture
def risk_engine(event_bus: EventBus, market_state: MarketState) -> RiskEngine:
    engine = RiskEngine(event_bus, market_state)
    market_state.account_snapshot.equity = 10_000
    market_state.account_snapshot.buying_power = 10_000
    return engine


def _signal(**overrides):
    base = {
        "strategy": "orb",
        "symbol": "AAPL",
        "direction": "long",
        "entry_price": 100.0,
        "stop_price": 90.0,
    }
    base.update(overrides)
    return base


def test_approves_valid_signal(risk_engine: RiskEngine):
    decision = risk_engine.evaluate(_signal())
    assert decision.approved
    # risk_amount = 10_000 * 1.25% = 125; stop_distance = 10 -> quantity = 12.5
    assert decision.quantity == pytest.approx(12.5)


def test_rejects_when_trading_disabled(risk_engine: RiskEngine):
    risk_engine.settings.trading_enabled = False
    decision = risk_engine.evaluate(_signal())
    assert not decision.approved
    assert decision.rejected_rule == "trading_enabled"


def test_rejects_when_max_positions_reached(risk_engine: RiskEngine, market_state: MarketState):
    risk_engine.settings.max_concurrent_positions = 1
    market_state.active_positions["MSFT"] = {"symbol": "MSFT", "quantity": 10, "entry_price": 50, "direction": "long"}
    decision = risk_engine.evaluate(_signal())
    assert not decision.approved
    assert decision.rejected_rule == "max_positions"


def test_rejects_duplicate_position(risk_engine: RiskEngine, market_state: MarketState):
    market_state.active_positions["AAPL"] = {"symbol": "AAPL", "quantity": 10, "entry_price": 100, "direction": "long"}
    decision = risk_engine.evaluate(_signal())
    assert not decision.approved
    assert decision.rejected_rule == "duplicate_position"


def test_rejects_strategy_allocation_exhausted(risk_engine: RiskEngine):
    risk_engine.settings.strategy_allocation = {"orb": 1.0}
    decision = risk_engine.evaluate(_signal(entry_price=1000.0, stop_price=990.0))
    assert not decision.approved
    assert decision.rejected_rule == "strategy_allocation"
