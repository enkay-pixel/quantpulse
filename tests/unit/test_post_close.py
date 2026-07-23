"""The options repair sensor must not fire before the close.

Yahoo's IV is stale until the session has traded (≈2.1% pre-market vs ≈33% post-close),
so a "repair" run in the morning would fill the missing tickers with junk while the
already-captured ones hold good marks — one snapshot_date, two qualities of data.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from quantpulse.orchestration.catchup import NEW_YORK, is_post_close

# 2026-07-23 is a Thursday; 2026-07-25 a Saturday.
TRADING_DAY = dt.date(2026, 7, 23)
WEEKEND = dt.date(2026, 7, 25)


def at(day: dt.date, hour: int, tz: ZoneInfo = NEW_YORK) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, tzinfo=tz)


def test_premarket_is_not_post_close() -> None:
    """The case that actually occurred: a repair queued at 06:00 ET."""
    assert not is_post_close(at(TRADING_DAY, 6))


def test_during_session_is_not_post_close() -> None:
    assert not is_post_close(at(TRADING_DAY, 11))


def test_after_the_close_is_allowed() -> None:
    assert is_post_close(at(TRADING_DAY, 16))
    assert is_post_close(at(TRADING_DAY, 19))  # when the daily job runs
    assert is_post_close(at(TRADING_DAY, 23))


def test_weekend_is_never_post_close() -> None:
    """No session traded, so there is nothing whose IV became meaningful."""
    assert not is_post_close(at(WEEKEND, 19))


def test_utc_input_is_converted_not_compared_raw() -> None:
    """23:00 UTC is 19:00 ET — post-close. Comparing the raw UTC hour would say no."""
    assert is_post_close(dt.datetime(2026, 7, 23, 23, tzinfo=dt.UTC))
    # 10:00 UTC is 06:00 ET — pre-market, despite the UTC hour looking mid-morning.
    assert not is_post_close(dt.datetime(2026, 7, 23, 10, tzinfo=dt.UTC))


def test_naive_datetime_is_treated_as_new_york() -> None:
    assert is_post_close(dt.datetime(2026, 7, 23, 19))
    assert not is_post_close(dt.datetime(2026, 7, 23, 6))
