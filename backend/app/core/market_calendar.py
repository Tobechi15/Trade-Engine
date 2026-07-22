from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.core.time_service import EXCHANGE_TZ, TimeService

# NOTE: hardcoded NYSE holiday/half-day calendar for 2025-2026. This is a
# pragmatic default, not a general solar/lunar holiday calculator - extend
# this table yearly (or swap in a maintained calendar package such as
# `pandas-market-calendars` if broader date coverage is needed).
NYSE_HOLIDAYS: set[date] = {
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1),
    date(2025, 11, 27), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
}

NYSE_HALF_DAYS: set[date] = {
    date(2025, 7, 3), date(2025, 11, 28), date(2025, 12, 24),
    date(2026, 11, 27), date(2026, 12, 24),
}

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
HALF_DAY_CLOSE = time(13, 0)
PRE_MARKET_OPEN = time(4, 0)
POST_MARKET_CLOSE = time(20, 0)


class MarketCalendarService:
    """Owns all trading schedule knowledge. Strategies must never call
    datetime.now() directly - they ask this service instead."""

    def is_market_day(self, d: date | None = None) -> bool:
        d = d or TimeService.now_exchange().date()
        return d.weekday() < 5 and d not in NYSE_HOLIDAYS

    def is_half_day(self, d: date | None = None) -> bool:
        d = d or TimeService.now_exchange().date()
        return d in NYSE_HALF_DAYS

    def _close_time(self, d: date) -> time:
        return HALF_DAY_CLOSE if self.is_half_day(d) else REGULAR_CLOSE

    def is_open(self, dt: datetime | None = None) -> bool:
        dt = TimeService.to_exchange(dt) if dt else TimeService.now_exchange()
        if not self.is_market_day(dt.date()):
            return False
        return REGULAR_OPEN <= dt.time() < self._close_time(dt.date())

    def is_pre_market(self, dt: datetime | None = None) -> bool:
        dt = TimeService.to_exchange(dt) if dt else TimeService.now_exchange()
        if not self.is_market_day(dt.date()):
            return False
        return PRE_MARKET_OPEN <= dt.time() < REGULAR_OPEN

    def is_post_market(self, dt: datetime | None = None) -> bool:
        dt = TimeService.to_exchange(dt) if dt else TimeService.now_exchange()
        if not self.is_market_day(dt.date()):
            return False
        return self._close_time(dt.date()) <= dt.time() < POST_MARKET_CLOSE

    def next_open(self, dt: datetime | None = None) -> datetime:
        dt = TimeService.to_exchange(dt) if dt else TimeService.now_exchange()
        candidate = dt.date()
        while True:
            if self.is_market_day(candidate):
                open_dt = datetime.combine(candidate, REGULAR_OPEN, tzinfo=EXCHANGE_TZ)
                if open_dt > dt:
                    return open_dt
            candidate += timedelta(days=1)

    def next_close(self, dt: datetime | None = None) -> datetime:
        dt = TimeService.to_exchange(dt) if dt else TimeService.now_exchange()
        if self.is_market_day(dt.date()):
            close_dt = datetime.combine(dt.date(), self._close_time(dt.date()), tzinfo=EXCHANGE_TZ)
            if close_dt > dt:
                return close_dt
        candidate = dt.date() + timedelta(days=1)
        while not self.is_market_day(candidate):
            candidate += timedelta(days=1)
        return datetime.combine(candidate, self._close_time(candidate), tzinfo=EXCHANGE_TZ)

    def time_until_open(self, dt: datetime | None = None) -> timedelta:
        dt = TimeService.to_exchange(dt) if dt else TimeService.now_exchange()
        return self.next_open(dt) - dt

    def time_until_close(self, dt: datetime | None = None) -> timedelta:
        dt = TimeService.to_exchange(dt) if dt else TimeService.now_exchange()
        return self.next_close(dt) - dt


market_calendar = MarketCalendarService()
