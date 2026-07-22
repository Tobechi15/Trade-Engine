from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

EXCHANGE_TZ = ZoneInfo("America/New_York")


class TimeService:
    """Single source of truth for time. Internal time is always UTC;
    exchange-local time (America/New_York) is derived from it. The dashboard
    is responsible for converting to the viewer's local timezone for display
    only - nothing server-side should reason in local wall-clock time.
    """

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def now_exchange() -> datetime:
        return datetime.now(EXCHANGE_TZ)

    @staticmethod
    def to_exchange(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(EXCHANGE_TZ)

    @staticmethod
    def to_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=EXCHANGE_TZ)
        return dt.astimezone(UTC)
