from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.indicators import BarResampler, VWAPState, adx, atr
from app.market_data.base import Bar

ET = ZoneInfo("America/New_York")


def test_vwap_state_basic():
    state = VWAPState()
    state.update(price=100.0, volume=10)
    state.update(price=102.0, volume=10)
    assert state.vwap == pytest.approx(101.0)
    assert state.std_dev == pytest.approx(1.0)


def test_vwap_state_bands_widen_with_dispersion():
    tight = VWAPState()
    tight.update(100.0, 10)
    tight.update(100.5, 10)

    wide = VWAPState()
    wide.update(90.0, 10)
    wide.update(110.0, 10)

    tight_upper, _ = tight.band(2.0)
    wide_upper, _ = wide.band(2.0)
    assert wide_upper - wide.vwap > tight_upper - tight.vwap


def test_bar_resampler_emits_completed_bucket_on_five_minutes():
    resampler = BarResampler(minutes=5)
    base = datetime(2026, 7, 22, 9, 30, tzinfo=ET)

    def payload(minute_offset: int, o, h, l, c, v):
        ts = base.replace(minute=30 + minute_offset) if minute_offset < 30 else base
        return {"symbol": "SPY", "timestamp": ts.isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": v}

    # 09:30, 09:31, 09:32, 09:33, 09:34 -> all in the same 5-min bucket
    for i in range(5):
        result = resampler.add("SPY", payload(i, 100 + i, 101 + i, 99 + i, 100.5 + i, 1000))
        assert result is None

    # 09:35 starts a new bucket -> should emit the completed [09:30,09:35) bucket
    completed = resampler.add("SPY", payload(5, 105, 106, 104, 105.5, 1000))
    assert completed is not None
    assert completed.open == 100  # open of the 09:30 candle
    assert completed.high == 105  # max high seen across 09:30-09:34
    assert completed.low == 99  # min low seen across 09:30-09:34
    assert completed.close == 104.5  # close of the last (09:34) candle in the bucket
    assert completed.volume == 5000


_BASE = datetime(2026, 7, 22, 9, 30, tzinfo=ET)


def _trending_bars(n: int) -> list[Bar]:
    bars = []
    price = 100.0
    for i in range(n):
        price += 1.0  # steadily trending up
        bars.append(Bar(symbol="QQQ", timestamp=_BASE + timedelta(minutes=i), open=price - 1, high=price + 0.5, low=price - 1.5, close=price, volume=1000))
    return bars


def _choppy_bars(n: int) -> list[Bar]:
    bars = []
    for i in range(n):
        price = 100.0 + (1 if i % 2 == 0 else -1)
        bars.append(Bar(symbol="QQQ", timestamp=_BASE + timedelta(minutes=i), open=100.0, high=price + 0.5, low=price - 0.5, close=price, volume=1000))
    return bars


def test_adx_higher_for_trending_than_choppy_market():
    trending_adx = adx(_trending_bars(40), period=14)
    choppy_adx = adx(_choppy_bars(40), period=14)
    assert trending_adx is not None
    assert choppy_adx is not None
    assert trending_adx > choppy_adx


def test_adx_none_with_insufficient_history():
    assert adx(_trending_bars(10), period=14) is None


def test_atr_basic():
    bars = [
        Bar(symbol="SPY", timestamp=datetime(2026, 7, 22, 9, 30, tzinfo=ET), open=100, high=102, low=99, close=101, volume=100),
        Bar(symbol="SPY", timestamp=datetime(2026, 7, 22, 9, 31, tzinfo=ET), open=101, high=103, low=100, close=102, volume=100),
    ]
    # true range for bar[1]: max(high-low=3, |high-prev_close|=|103-101|=2, |low-prev_close|=|100-101|=1) = 3
    value = atr(bars, period=14)
    assert value == pytest.approx(3.0)
