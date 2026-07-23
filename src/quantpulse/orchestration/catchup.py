"""Detect trading days the pipeline slept through.

Schedules only fire while the stack is up, and this runs on a laptop. Rather than
silently losing those sessions, compare expected NYSE sessions against what actually
landed in `prices` and let the catch-up sensor request the gaps.
"""

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import text

from quantpulse.data.calendar import is_trading_day
from quantpulse.db import get_engine

logger = logging.getLogger(__name__)

# A session counts as ingested only if a healthy share of the universe arrived; a
# partially-written day should be retried, not treated as done.
MIN_COVERAGE = 0.8

NEW_YORK = ZoneInfo("America/New_York")
MARKET_CLOSE_HOUR_ET = 16  # NYSE closes 16:00 ET; IV is only meaningful after it


def missing_trading_days(expected: list[dt.date]) -> list[dt.date]:
    """Which of `expected` sessions lack adequate price coverage, oldest first."""
    if not expected:
        return []
    with get_engine().connect() as conn:
        universe_size = conn.execute(
            text("SELECT count(*) FROM universe WHERE active")
        ).scalar_one()
        rows = conn.execute(
            text(
                "SELECT date, count(*) AS n FROM prices "
                "WHERE date >= :start AND date <= :end GROUP BY date"
            ),
            {"start": min(expected), "end": max(expected)},
        ).all()
    if not universe_size:
        return []

    counts = {row.date: row.n for row in rows}
    threshold = universe_size * MIN_COVERAGE
    missing = [day for day in sorted(expected) if counts.get(day, 0) < threshold]
    if missing:
        logger.info("Catch-up: %d session(s) below coverage: %s", len(missing), missing[:5])
    return missing


def is_post_close(now: dt.datetime | None = None) -> bool:
    """Is it after the NYSE close on a trading day, in New York time?

    Yahoo's implied volatility is only trustworthy once the session has traded: measured
    on this universe, post-close averages ≈33% ATM IV against ≈2.1% pre-market. A repair
    that runs at 06:00 would therefore *degrade* a partial snapshot — filling the missing
    tickers with junk while the ones already captured hold good post-close marks, leaving
    a single snapshot_date with two incompatible qualities of data in it.
    """
    now = now or dt.datetime.now(NEW_YORK)
    if now.tzinfo is None:
        now = now.replace(tzinfo=NEW_YORK)
    local = now.astimezone(NEW_YORK)
    return is_trading_day(local.date()) and local.hour >= MARKET_CLOSE_HOUR_ET


def option_snapshot_incomplete(today: dt.date) -> float | None:
    """Coverage of *today's* option snapshot when it is below par, else None.

    Deliberately today-only. Option chains are live-only — re-running tomorrow
    snapshots tomorrow's chains, so a thin past day is a permanent hole and there is
    nothing to repair. An interrupted run *today* is the one case that can still be
    salvaged, because `snapshot_option_chains` commits per ticker and upserts on
    (snapshot_date, ticker, ...), so a re-run fills the gaps it left.

    Callers must also gate on `is_post_close()` — coverage says a repair is *possible*,
    not that now is a sane moment to attempt one.
    """
    with get_engine().connect() as conn:
        universe_size = conn.execute(
            text("SELECT count(*) FROM universe WHERE active")
        ).scalar_one()
        covered = conn.execute(
            text("SELECT count(DISTINCT ticker) FROM option_quotes WHERE snapshot_date = :day"),
            {"day": today},
        ).scalar_one()
    if not universe_size or not covered:
        return None  # nothing snapshotted yet today — that is the schedule's job, not repair
    coverage = covered / universe_size
    return coverage if coverage < MIN_COVERAGE else None
