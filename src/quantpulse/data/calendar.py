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
    # Share of the universe taken on each side of a long/short book. Set from breadth so
    # every market holds a comparable NUMBER of positions, not a comparable percentile:
    # 20% of 50 US names and 35% of 29 JSE names are both ~10 per side. A thin market
    # sliced at 20% would hold 6, roughly doubling per-position idiosyncratic risk.
    quantile_width: float = 0.2
    # How much better a challenger's IC must be to count as better rather than luckier.
    # Measured, not chosen: refit the same specification with only the RNG changed and the
    # holdout IC moves with sd ~0.003 (XNYS) / ~0.004 (XJSE); this is 2 sd. Sharpe is far
    # noisier (sd 0.12 / 0.24 on the same experiment, and ~2.0 across six-month windows),
    # which is why the gate compares IC and keeps Sharpe only as a floor. Re-measure with
    # the variance study when the panel or the evaluation code changes materially.
    ic_promotion_margin: float = 0.006
    # Features this market trains on. Empty means every engineered column, which is what
    # both markets currently use.
    #
    # The field was added because a drop-one sweep and a forward selection both found
    # `vol_63` helping one market and hurting the other at fixed hyperparameters. That
    # premise did not survive re-measurement (2026-09-01): re-run across 49 rolling
    # origins rather than four fixed folds, the drop-one delta for `vol_63` is +0.0100
    # (t +0.7) on XNYS and +0.0030 (t +0.2) on XJSE, down from t +9.14 and t -5.35. The
    # markets are not shown to disagree about it, or about any feature. The field still
    # earns its place for the pruning result below, which was measured with tuning in the
    # loop, but not for the disagreement it was named after.
    #
    # Re-checked at sixteen seeds, pruning XNYS to vol_21 does hold up: paired
    # +0.0133 +/- 0.0044 (t +3.00), eleven of sixteen seeds positive. XJSE is unresolved at
    # t +1.16 and would need about twenty-four.
    #
    # Still empty on both, because a resolved effect is not the same as a decision: vol_21
    # was selected on this panel, and +0.0133 is smaller than the round-to-round spread that
    # early stopping already contributes. Set this on evidence from a fresh panel period,
    # gathered with tuning in the loop the way the promotion gate trains.
    #
    # Names are validated against the engineered columns at resolution time, so a typo
    # fails loudly instead of quietly training on a shorter list.
    feature_columns: tuple[str, ...] = ()

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
    quantile_width=0.35,  # 29 names -> ~10 per side, matching XNYS
    ic_promotion_margin=0.008,  # 2 sd; a thinner cross-section re-rolls wider than XNYS
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
