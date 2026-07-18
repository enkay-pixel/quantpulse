import datetime as dt

from quantpulse.data.calendar import is_trading_day, last_trading_day, trading_days


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
