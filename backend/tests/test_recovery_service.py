import asyncio

import pytest

from app.services.recovery_service import BACKOFF_SCHEDULE_SECONDS, RecoveryService


@pytest.mark.asyncio
async def test_backoff_grows_on_repeated_fast_failures(event_bus, monkeypatch):
    """Regression test: a stream that fails instantly every time (e.g. bad
    credentials, wrong URL) must back off with growing delays, not reset
    to the fast end each cycle - that reset-on-any-attempt bug caused the
    supervisor to retry roughly once a second forever, which is what
    tripped Massive's rate limit in production."""
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    service = RecoveryService(event_bus, broker=object(), market_data_service=object(), order_manager=object())

    call_count = 0

    async def instantly_failing_stream() -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= 4:
            raise asyncio.CancelledError()
        raise RuntimeError("auth failed")

    with pytest.raises(asyncio.CancelledError):
        await service._supervise("broker", instantly_failing_stream)

    # Delays must strictly grow (never reset to the first entry) across
    # consecutive fast failures.
    assert sleeps == BACKOFF_SCHEDULE_SECONDS[:3]


@pytest.mark.asyncio
async def test_backoff_resets_after_a_stable_connection(event_bus, monkeypatch):
    """A connection that stays up for a while before dropping should be
    treated as a fresh failure (fast retry), not penalized with a long
    backoff carried over from before it connected."""
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    service = RecoveryService(event_bus, broker=object(), market_data_service=object(), order_manager=object())
    service._reconnect_attempts["broker"] = 3  # simulate prior fast-failure streak

    import app.services.recovery_service as recovery_module

    times = iter([0.0, 100.0, 100.0, 130.0])  # 30s stable run, then instant failure

    class FakeDatetime:
        @staticmethod
        def now(tz):
            from datetime import datetime as real_datetime

            return real_datetime.fromtimestamp(next(times), tz=tz)

    monkeypatch.setattr(recovery_module, "datetime", FakeDatetime)

    call_count = 0

    async def stream() -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()
        raise RuntimeError("dropped after being connected a while")

    with pytest.raises(asyncio.CancelledError):
        await service._supervise("broker", stream)

    # Ran for 30s (>= STABLE_CONNECTION_SECONDS) before failing, so the
    # very next backoff should be the fast-end delay, not a continuation
    # of the earlier 3-attempt streak.
    assert sleeps == [BACKOFF_SCHEDULE_SECONDS[0]]
