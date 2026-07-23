"""Detect trading days the pipeline slept through.

Schedules only fire while the stack is up, and this runs on a laptop. Rather than
silently losing those sessions, compare the exchange's expected sessions against what
actually landed in `prices` and let the catch-up sensor request the gaps.
"""

import datetime as dt
import logging

from sqlalchemy import text

# Re-exported: is_post_close became exchange-aware and now lives with the registry, but
# the sensors import it from here.
from quantpulse.data.calendar import (
    DEFAULT_EXCHANGE,
    is_post_close,  # noqa: F401
)
from quantpulse.db import get_engine

logger = logging.getLogger(__name__)

# A session counts as ingested only if a healthy share of the universe arrived; a
# partially-written day should be retried, not treated as done.
MIN_COVERAGE = 0.8


def missing_trading_days(
    expected: list[dt.date], exchange: str = DEFAULT_EXCHANGE
) -> list[dt.date]:
    """Which of `expected` sessions lack adequate price coverage, oldest first.

    Scoped to one exchange: coverage is a fraction of *that* market's universe, and its
    holidays are its own. Counting a JSE holiday against NYSE coverage would request
    catch-up runs forever.
    """
    if not expected:
        return []
    with get_engine().connect() as conn:
        universe_size = conn.execute(
            text("SELECT count(*) FROM universe WHERE active AND exchange = :ex"),
            {"ex": exchange},
        ).scalar_one()
        rows = conn.execute(
            text(
                "SELECT p.date, count(*) AS n FROM prices p "
                "JOIN universe u ON u.ticker = p.ticker AND u.exchange = :ex "
                "WHERE p.date >= :start AND p.date <= :end GROUP BY p.date"
            ),
            {"start": min(expected), "end": max(expected), "ex": exchange},
        ).all()
    if not universe_size:
        return []

    counts = {row.date: row.n for row in rows}
    threshold = universe_size * MIN_COVERAGE
    missing = [day for day in sorted(expected) if counts.get(day, 0) < threshold]
    if missing:
        logger.info("Catch-up: %d session(s) below coverage: %s", len(missing), missing[:5])
    return missing


def option_snapshot_incomplete(today: dt.date, exchange: str = DEFAULT_EXCHANGE) -> float | None:
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
            text("SELECT count(*) FROM universe WHERE active AND exchange = :ex"),
            {"ex": exchange},
        ).scalar_one()
        covered = conn.execute(
            text(
                "SELECT count(DISTINCT o.ticker) FROM option_quotes o "
                "JOIN universe u ON u.ticker = o.ticker AND u.exchange = :ex "
                "WHERE o.snapshot_date = :day"
            ),
            {"day": today, "ex": exchange},
        ).scalar_one()
    if not universe_size or not covered:
        return None  # nothing snapshotted yet today — that is the schedule's job, not repair
    coverage = covered / universe_size
    return coverage if coverage < MIN_COVERAGE else None
