from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.market_calendar import MarketCalendarService

ET = ZoneInfo("America/New_York")


def test_is_market_day_weekday_non_holiday():
    calendar = MarketCalendarService()
    tuesday = datetime(2026, 7, 21, tzinfo=ET).date()
    assert calendar.is_market_day(tuesday)


def test_is_market_day_weekend():
    calendar = MarketCalendarService()
    saturday = datetime(2026, 7, 25, tzinfo=ET).date()
    assert not calendar.is_market_day(saturday)


def test_is_market_day_holiday():
    calendar = MarketCalendarService()
    christmas = datetime(2026, 12, 25, tzinfo=ET).date()
    assert not calendar.is_market_day(christmas)


def test_is_open_during_regular_hours():
    calendar = MarketCalendarService()
    during = datetime(2026, 7, 21, 10, 0, tzinfo=ET)
    assert calendar.is_open(during)


def test_is_open_before_open():
    calendar = MarketCalendarService()
    before = datetime(2026, 7, 21, 9, 0, tzinfo=ET)
    assert not calendar.is_open(before)
    assert calendar.is_pre_market(before)


def test_half_day_closes_early():
    calendar = MarketCalendarService()
    half_day_afternoon = datetime(2026, 11, 27, 14, 0, tzinfo=ET)
    assert not calendar.is_open(half_day_afternoon)
