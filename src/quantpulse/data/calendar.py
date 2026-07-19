"""NYSE trading-calendar helpers."""

import datetime as dt
from functools import lru_cache

import exchange_calendars as xcals


@lru_cache
def _nyse() -> xcals.ExchangeCalendar:
    return xcals.get_calendar("XNYS")


def trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    """All NYSE sessions in [start, end], inclusive."""
    sessions = _nyse().sessions_in_range(str(start), str(end))
    return [s.date() for s in sessions]


def is_trading_day(day: dt.date) -> bool:
    return _nyse().is_session(str(day))


def last_trading_day(asof: dt.date | None = None) -> dt.date:
    """Most recent NYSE session on or before `asof` (default: today)."""
    asof = asof or dt.date.today()
    return _nyse().date_to_session(str(asof), direction="previous").date()
