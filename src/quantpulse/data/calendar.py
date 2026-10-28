"""Exchange registry and trading-calendar helpers.

Every market fact — calendar, timezone, close hour, currency, benchmark, whether free
option chains exist — lives on an `Exchange` here rather than as a constant somewhere.
Callers pass an exchange code; the default keeps single-market behaviour identical.
"""

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Exchange:
    """One market's calendar, clock, currency and benchmark."""

    code: str  # our key, and the exchange_calendars name
    # The market's plain name, by the city it trades in. The dashboard's market menu shows it
    # beside the code: with seven markets, four-letter codes such as XSWX alone are a quiz.
    display_name: str
    timezone: str
    close_hour: int  # local hour the session ends; IV/marks are only meaningful after it
    currency: str  # quote currency as the data vendor reports it
    benchmark: str  # buy-and-hold comparison ticker
    has_options: bool  # free option chains available from the vendor
    # How much better a challenger's IC must be to count as better rather than luckier: 2 sd of
    # the gate's holdout IC when the champion's specification is refitted with only the seed
    # changed. Sharpe is far noisier, which is why the gate compares IC and keeps Sharpe only as
    # a floor. No default: a market states its value, and measures it before its first challenger
    # is judged (method and readings in docs/findings/promotion-margin.md). Re-measure whenever
    # the panel, the training code or early stopping changes: a change to early stopping once
    # tripled one market's spread and left its margin a third of the noise for weeks.
    ic_promotion_margin: float
    display_divisor: float = 1.0  # quote units per display unit (JSE quotes in cents)
    display_symbol: str = "$"
    # Share of the universe taken on each side of a long/short book. Set from breadth so
    # every market holds a comparable NUMBER of positions, not a comparable percentile:
    # 20% of 50 US names and 35% of 29 JSE names are both ~10 per side. A thin market
    # sliced at 20% would hold 6, roughly doubling per-position idiosyncratic risk.
    quantile_width: float = 0.2
    # Features this market trains on. Empty means every engineered column, which is what
    # both markets currently use.
    #
    # A market carries its own list only when the evidence shows a subset serves it better,
    # and that evidence has to come from a panel period other than the one the subset was
    # chosen on, measured with tuning in the loop the way the promotion gate trains. An effect
    # found and selected on the same panel is not yet a decision, and it can be smaller than
    # the variation early stopping already introduces between fits. The measurements behind
    # leaving both markets empty are in docs/findings/feature-ablation-and-pruning.md.
    #
    # Names are validated against the engineered columns at resolution time, so a typo
    # fails loudly instead of quietly training on a shorter list.
    feature_columns: tuple[str, ...] = ()
    # Highest learning rate the tuner may search. The tuner scores candidates on walk-forward
    # folds that exclude the promotion holdout, and where the fastest learning rates win those
    # folds without generalising, a small trial budget finds them reliably and the candidate
    # then scores well below a slower one on the holdout. A lower ceiling removes that region
    # from the search instead of relying on the budget to avoid it.
    #
    # Per market because the markets differ: a ceiling helps where the tuner tends to
    # overshoot and costs a little where it rarely does. The evidence behind each value is in
    # docs/findings/learning-rate-ceiling.md; re-measure there before changing one.
    learning_rate_ceiling: float = 0.2

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


XNYS = Exchange(
    code="XNYS",
    display_name="New York",
    timezone="America/New_York",
    close_hour=16,
    currency="USD",
    benchmark="SPY",
    has_options=True,
    ic_promotion_margin=0.009,
)

XJSE = Exchange(
    code="XJSE",
    display_name="Johannesburg",
    timezone="Africa/Johannesburg",
    close_hour=17,
    currency="ZAc",  # South African cents: a 79787 quote is R797.87
    benchmark="STX40.JO",
    has_options=False,  # no free JSE chain data exists from any vendor we can use
    display_divisor=100.0,
    display_symbol="R",
    quantile_width=0.35,  # 29 names -> ~10 per side, matching XNYS
    ic_promotion_margin=0.026,  # stops after few rounds, so the round count re-rolls with the seed
    learning_rate_ceiling=0.02,  # the tuner overshoots on this market; see the finding
)

XLON = Exchange(
    code="XLON",
    display_name="London",
    timezone="Europe/London",
    close_hour=17,  # the session ends 16:30; the first whole hour after it
    currency="GBp",  # pence: a 1428 quote is £14.28
    benchmark="ISF.L",  # iShares Core FTSE 100
    has_options=False,  # no free London chain data
    ic_promotion_margin=0.027,  # its champion keeps one or two rounds, so it re-rolls wide
    learning_rate_ceiling=0.02,  # the tuner overshoots here as on the JSE; see the finding
    display_divisor=100.0,
    display_symbol="£",
    quantile_width=0.25,  # 40 names -> 10 per side, matching the other markets
)

# The first wave of more markets (docs/plans/m13-europe-wave.md). Each European session ends at
# 17:30 local time, so the first whole hour after it is 18. Their margins and ceilings were
# measured on 2026-10-28, before the first challenger (the plan's phase 5). None of the four
# needed a ceiling, so all keep the default 0.2; see both findings for the readings.
XETR = Exchange(
    code="XETR",
    display_name="Frankfurt",
    timezone="Europe/Berlin",
    close_hour=18,  # Xetra ends 17:30
    currency="EUR",
    benchmark="EXS1.DE",  # iShares Core DAX
    has_options=False,  # no free Eurex chain data
    ic_promotion_margin=0.006,  # no champion yet: measured on what its tuner chose
    display_symbol="€",
    quantile_width=0.25,  # 40 names -> 10 per side
)

XPAR = Exchange(
    code="XPAR",
    display_name="Paris",
    timezone="Europe/Paris",
    close_hour=18,  # Euronext ends 17:30
    currency="EUR",
    benchmark="CAC.PA",  # Amundi CAC 40
    has_options=False,
    ic_promotion_margin=0.017,  # no champion yet: measured on what its tuner chose
    display_symbol="€",
    quantile_width=0.25,  # 40 names -> 10 per side
)

XSWX = Exchange(
    code="XSWX",
    display_name="Zurich",
    timezone="Europe/Zurich",
    close_hour=18,  # SIX ends 17:30
    currency="CHF",
    benchmark="CSSMI.SW",  # iShares SMI
    has_options=False,
    ic_promotion_margin=0.023,  # measured on its champion v1's specification
    display_symbol="CHF ",  # a word, not a sign, so it needs the space: CHF 12.50
    quantile_width=0.25,  # 37 names -> 9 per side
)

XAMS = Exchange(
    code="XAMS",
    display_name="Amsterdam",
    timezone="Europe/Amsterdam",
    close_hour=18,  # Euronext ends 17:30
    currency="EUR",
    benchmark="IAEX.AS",  # iShares AEX
    has_options=False,
    ic_promotion_margin=0.031,  # no champion yet: measured on what its tuner chose
    display_symbol="€",
    quantile_width=0.33,  # 30 names -> 10 per side, as the JSE takes 35% of 29
)


EXCHANGES: dict[str, Exchange] = {e.code: e for e in (XNYS, XJSE, XLON, XETR, XPAR, XSWX, XAMS)}
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


def last_closed_session(now: dt.datetime | None = None, exchange: str | None = None) -> dt.date:
    """Newest session of this exchange that had closed by `now`.

    `last_trading_day` goes by the date alone, so until the close it returns a session still to
    finish, whose close the vendor reports as the live price. A session counts as closed when
    `is_post_close` says so, from the exchange's `close_hour`.
    """
    ex = get_exchange(exchange)
    now = now or dt.datetime.now(ex.tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ex.tz)
    today = now.astimezone(ex.tz).date()
    if is_post_close(now, ex.code):
        return today
    return last_trading_day(today - dt.timedelta(days=1), ex.code)


def session_in_progress(now: dt.datetime | None = None, exchange: str | None = None) -> bool:
    """Is one of this exchange's sessions trading at `now`?

    Read from the calendar's own open and close for the day, so early closes and holidays
    come out right without an opening hour being kept here as well.
    """
    ex = get_exchange(exchange)
    now = now or dt.datetime.now(ex.tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ex.tz)
    cal = _calendar(ex.code)
    day = now.astimezone(ex.tz).date()
    if not cal.is_session(str(day)):
        return False
    opens, closes = cal.session_open_close(str(day))
    return bool(opens <= pd.Timestamp(now) < closes)
