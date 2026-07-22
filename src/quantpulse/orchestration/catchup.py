"""Detect trading days the pipeline slept through.

Schedules only fire while the stack is up, and this runs on a laptop. Rather than
silently losing those sessions, compare expected NYSE sessions against what actually
landed in `prices` and let the catch-up sensor request the gaps.
"""

import datetime as dt
import logging

from sqlalchemy import text

from quantpulse.db import get_engine

logger = logging.getLogger(__name__)

# A session counts as ingested only if a healthy share of the universe arrived; a
# partially-written day should be retried, not treated as done.
MIN_COVERAGE = 0.8


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


def option_snapshot_incomplete(today: dt.date) -> float | None:
    """Coverage of *today's* option snapshot when it is below par, else None.

    Deliberately today-only. Option chains are live-only — re-running tomorrow
    snapshots tomorrow's chains, so a thin past day is a permanent hole and there is
    nothing to repair. An interrupted run *today* is the one case that can still be
    salvaged, because `snapshot_option_chains` commits per ticker and upserts on
    (snapshot_date, ticker, ...), so a re-run fills the gaps it left.
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
