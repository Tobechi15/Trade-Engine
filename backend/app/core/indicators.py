from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.time_service import TimeService
from app.market_data.base import Bar


def true_range(prev_close: float, bar: Bar) -> float:
    return max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))


def atr(bars: list[Bar], period: int) -> float:
    if len(bars) < 2:
        return 0.0
    trs = [true_range(bars[i - 1].close, bars[i]) for i in range(1, len(bars))]
    window = trs[-period:] if len(trs) >= period else trs
    return sum(window) / len(window) if window else 0.0


def _wilder_smooth(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    smoothed = [sum(values[:period])]
    for v in values[period:]:
        smoothed.append(smoothed[-1] - (smoothed[-1] / period) + v)
    return smoothed


def adx(bars: list[Bar], period: int = 14) -> float | None:
    """Wilder's Average Directional Index. Returns None if there isn't
    enough history yet (needs roughly 2x period bars)."""
    if len(bars) < period * 2:
        return None
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    trs: list[float] = []
    for i in range(1, len(bars)):
        up_move = bars[i].high - bars[i - 1].high
        down_move = bars[i - 1].low - bars[i].low
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        trs.append(true_range(bars[i - 1].close, bars[i]))

    tr_s = _wilder_smooth(trs, period)
    pdm_s = _wilder_smooth(plus_dm, period)
    mdm_s = _wilder_smooth(minus_dm, period)

    dxs: list[float] = []
    for tr_v, pdm_v, mdm_v in zip(tr_s, pdm_s, mdm_s):
        if tr_v == 0:
            dxs.append(0.0)
            continue
        plus_di = 100 * pdm_v / tr_v
        minus_di = 100 * mdm_v / tr_v
        total = plus_di + minus_di
        dxs.append(100 * abs(plus_di - minus_di) / total if total else 0.0)

    adx_series = _wilder_smooth(dxs, period)
    return adx_series[-1] if adx_series else None


@dataclass(slots=True)
class VWAPState:
    """Session-anchored VWAP with volume-weighted standard deviation bands.
    Reset at market open - never carries over between sessions."""

    cumulative_pv: float = 0.0
    cumulative_volume: float = 0.0
    cumulative_pv2: float = 0.0

    def update(self, price: float, volume: float) -> None:
        self.cumulative_pv += price * volume
        self.cumulative_volume += volume
        self.cumulative_pv2 += volume * price * price

    @property
    def vwap(self) -> float:
        return self.cumulative_pv / self.cumulative_volume if self.cumulative_volume else 0.0

    @property
    def std_dev(self) -> float:
        if self.cumulative_volume == 0:
            return 0.0
        mean = self.vwap
        variance = max(0.0, self.cumulative_pv2 / self.cumulative_volume - mean * mean)
        return math.sqrt(variance)

    def band(self, num_std: float) -> tuple[float, float]:
        """Returns (upper, lower)."""
        sd = self.std_dev
        return self.vwap + num_std * sd, self.vwap - num_std * sd

    def reset(self) -> None:
        self.cumulative_pv = 0.0
        self.cumulative_volume = 0.0
        self.cumulative_pv2 = 0.0


@dataclass(slots=True)
class BarBucket:
    open: float
    high: float
    low: float
    close: float
    volume: float
    start: datetime

    def to_bar(self, symbol: str) -> Bar:
        return Bar(symbol=symbol, timestamp=self.start, open=self.open, high=self.high, low=self.low, close=self.close, volume=self.volume)


def _bucket_start(exchange_time: datetime, minutes: int) -> datetime:
    session_open = exchange_time.replace(hour=9, minute=30, second=0, microsecond=0)
    elapsed_minutes = int((exchange_time - session_open).total_seconds() // 60)
    bucket_index = max(0, elapsed_minutes // minutes)
    return session_open + timedelta(minutes=bucket_index * minutes)


class BarResampler:
    """Aggregates a stream of 1-minute NEW_CANDLE payloads into N-minute
    bars, bucketed on session-open-aligned boundaries (e.g. 09:30-09:35,
    09:35-09:40, ...). Feed it one payload at a time; it returns the
    completed prior bucket exactly once, the moment a new bucket starts -
    the same emit-on-close pattern the ORB strategy uses for its opening
    range."""

    def __init__(self, minutes: int) -> None:
        self.minutes = minutes
        self._buckets: dict[str, BarBucket] = {}

    def add(self, symbol: str, payload: dict) -> BarBucket | None:
        exchange_time = TimeService.to_exchange(datetime.fromisoformat(payload["timestamp"]))
        bucket_start = _bucket_start(exchange_time, self.minutes)
        current = self._buckets.get(symbol)

        if current is None or current.start != bucket_start:
            completed = current
            self._buckets[symbol] = BarBucket(
                open=payload["open"],
                high=payload["high"],
                low=payload["low"],
                close=payload["close"],
                volume=payload["volume"],
                start=bucket_start,
            )
            return completed

        current.high = max(current.high, payload["high"])
        current.low = min(current.low, payload["low"])
        current.close = payload["close"]
        current.volume += payload["volume"]
        return None

    def reset(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._buckets.clear()
        else:
            self._buckets.pop(symbol, None)
