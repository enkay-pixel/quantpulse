"""NYSE trading-calendar helpers."""

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

NEW_YORK = ZoneInfo("America/New_York")


@lru_cache
def _nyse() -> xcals.ExchangeCalendar:
    return xcals.get_calendar("XNYS")


def market_today() -> dt.date:
    """Today's date *in exchange time* — never the container's UTC date.

    Containers run UTC, so `date.today()` silently disagrees with the trading session for
    any run after 20:00 ET. Under EDT the 19:00 ET jobs land at 23:00 UTC and the two
    agree; under EST they land at **00:00 UTC**, and every row written that evening would
    be stamped with tomorrow's date. That shifts the whole options history by a day at the
    November DST change — invisibly, and in a dataset that cannot be rebuilt.
    """
    return dt.datetime.now(NEW_YORK).date()


def trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    """All NYSE sessions in [start, end], inclusive."""
    sessions = _nyse().sessions_in_range(str(start), str(end))
    return [s.date() for s in sessions]


def is_trading_day(day: dt.date) -> bool:
    return _nyse().is_session(str(day))


def last_trading_day(asof: dt.date | None = None) -> dt.date:
    """Most recent NYSE session on or before `asof` (default: today)."""
    asof = asof or market_today()
    return _nyse().date_to_session(str(asof), direction="previous").date()
