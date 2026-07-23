"""Exchange registry and trading-calendar helpers.

Every market fact that used to be a hardcoded NYSE constant — calendar, timezone, close
hour, currency, benchmark, whether free option chains exist — lives on an `Exchange` here.
Callers pass an exchange code; the default keeps single-market behaviour identical.
"""

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Exchange:
    """One market's calendar, clock, currency and benchmark."""

    code: str  # our key, and the exchange_calendars name
    timezone: str
    close_hour: int  # local hour the session ends; IV/marks are only meaningful after it
    currency: str  # quote currency as the data vendor reports it
    benchmark: str  # buy-and-hold comparison ticker
    has_options: bool  # free option chains available from the vendor
    display_divisor: float = 1.0  # quote units per display unit (JSE quotes in cents)
    display_symbol: str = "$"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


XNYS = Exchange(
    code="XNYS",
    timezone="America/New_York",
    close_hour=16,
    currency="USD",
    benchmark="SPY",
    has_options=True,
)

XJSE = Exchange(
    code="XJSE",
    timezone="Africa/Johannesburg",
    close_hour=17,
    currency="ZAc",  # South African cents: a 79787 quote is R797.87
    benchmark="STX40.JO",
    has_options=False,  # no free JSE chain data exists from any vendor we can use
    display_divisor=100.0,
    display_symbol="R",
)

EXCHANGES: dict[str, Exchange] = {e.code: e for e in (XNYS, XJSE)}
DEFAULT_EXCHANGE = XNYS.code


def get_exchange(code: str | None = None) -> Exchange:
    """Look up an exchange, defaulting to NYSE. Raises on an unknown code."""
    key = (code or DEFAULT_EXCHANGE).upper()
    try:
        return EXCHANGES[key]
    except KeyError:
        raise ValueError(f"Unknown exchange {key!r}; known: {sorted(EXCHANGES)}") from None


@lru_cache
def _calendar(code: str) -> xcals.ExchangeCalendar:
    return xcals.get_calendar(code)


def market_today(exchange: str | None = None) -> dt.date:
    """Today's date *in exchange time* — never the container's UTC date.

    Containers run UTC, so `date.today()` silently disagrees with the trading session for
    any run after the local day rolls over. Under EDT the 19:00 ET jobs land at 23:00 UTC
    and the two agree; under EST they land at **00:00 UTC**, and every row written that
    evening would be stamped with tomorrow's date. That shifts the whole options history by
    a day at the November DST change — invisibly, in a dataset that cannot be rebuilt.
    """
    return dt.datetime.now(get_exchange(exchange).tz).date()


def trading_days(start: dt.date, end: dt.date, exchange: str | None = None) -> list[dt.date]:
    """All sessions in [start, end], inclusive, for this exchange."""
    ex = get_exchange(exchange)
    return [s.date() for s in _calendar(ex.code).sessions_in_range(str(start), str(end))]


def is_trading_day(day: dt.date, exchange: str | None = None) -> bool:
    return _calendar(get_exchange(exchange).code).is_session(str(day))


def last_trading_day(asof: dt.date | None = None, exchange: str | None = None) -> dt.date:
    """Most recent session on or before `asof` (default: today in exchange time)."""
    ex = get_exchange(exchange)
    asof = asof or market_today(ex.code)
    return _calendar(ex.code).date_to_session(str(asof), direction="previous").date()


def is_post_close(now: dt.datetime | None = None, exchange: str | None = None) -> bool:
    """Is it after this exchange's close on one of its trading days?

    Vendor marks are only trustworthy once the session has traded: measured on the US
    universe, post-close averages ≈33% ATM IV against ≈2.1% pre-market.
    """
    ex = get_exchange(exchange)
    now = now or dt.datetime.now(ex.tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ex.tz)
    local = now.astimezone(ex.tz)
    return is_trading_day(local.date(), ex.code) and local.hour >= ex.close_hour
