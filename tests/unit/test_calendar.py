import datetime as dt

import pytest

from quantpulse.data.calendar import (
    XJSE,
    is_post_close,
    is_trading_day,
    last_closed_session,
    last_trading_day,
    session_in_progress,
    trading_days,
)


def test_trading_days_excludes_weekends_and_holidays() -> None:
    days = trading_days(dt.date(2024, 7, 1), dt.date(2024, 7, 8))
    # July 4th 2024 (Thursday) is closed; 6th/7th are the weekend.
    assert dt.date(2024, 7, 4) not in days
    assert days == [
        dt.date(2024, 7, 1),
        dt.date(2024, 7, 2),
        dt.date(2024, 7, 3),
        dt.date(2024, 7, 5),
        dt.date(2024, 7, 8),
    ]


def test_is_trading_day() -> None:
    assert is_trading_day(dt.date(2024, 7, 5))
    assert not is_trading_day(dt.date(2024, 7, 6))


def test_last_trading_day_rolls_back_from_weekend() -> None:
    assert last_trading_day(dt.date(2024, 7, 7)) == dt.date(2024, 7, 5)
    assert last_trading_day(dt.date(2024, 7, 5)) == dt.date(2024, 7, 5)


# Days the JSE did not trade that the library counts as sessions. Written out rather than read from
# the exchange, so that losing one from the list fails here.
JSE_CLOSURES = [
    dt.date(2021, 11, 1),
    dt.date(2022, 12, 27),
    dt.date(2023, 12, 15),
    dt.date(2024, 5, 29),
    dt.date(2026, 11, 4),
]


@pytest.mark.parametrize("day", JSE_CLOSURES)
def test_a_declared_jse_closure_is_not_a_session(day: dt.date) -> None:
    week = dt.timedelta(days=7)
    assert not is_trading_day(day, "XJSE")
    assert day not in trading_days(day - week, day + week, "XJSE")
    assert last_trading_day(day, "XJSE") < day


def test_the_closures_add_to_the_librarys_holidays_and_stay_in_their_market() -> None:
    assert is_trading_day(dt.date(2026, 11, 3), "XJSE")
    assert is_trading_day(dt.date(2026, 11, 5), "XJSE")
    assert not is_trading_day(dt.date(2026, 12, 25), "XJSE"), "a rule-based holiday was lost"
    assert not is_trading_day(dt.date(2019, 5, 8), "XJSE"), "the library's own one-off was lost"
    assert is_trading_day(dt.date(2026, 11, 4), "XLON")
    assert is_trading_day(dt.date(2026, 11, 4), "XNYS")


def test_a_closed_day_has_no_session_to_trade_or_to_close() -> None:
    """What every scheduled path asks of the clock: nothing is open, nothing has just closed, and
    the newest session to expect is the one before."""
    noon = dt.datetime(2026, 11, 4, 12, tzinfo=XJSE.tz)
    evening = dt.datetime(2026, 11, 4, 18, tzinfo=XJSE.tz)
    assert not session_in_progress(noon, "XJSE")
    assert not is_post_close(evening, "XJSE")
    assert last_closed_session(evening, "XJSE") == dt.date(2026, 11, 3)
