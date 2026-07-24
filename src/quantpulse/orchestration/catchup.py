"""Detect trading days the pipeline slept through.

Schedules only fire while the stack is up, and this runs on a laptop. Rather than
silently losing those sessions, compare the exchange's expected sessions against what
actually landed in `prices` and let the catch-up sensor request the gaps.
"""

import datetime as dt
import logging
from collections.abc import Iterable

from sqlalchemy import text

# Re-exported: is_post_close became exchange-aware and now lives with the registry, but
# the sensors import it from here.
from quantpulse.data.calendar import (
    DEFAULT_EXCHANGE,
    is_post_close,  # noqa: F401
)
from quantpulse.db import get_engine

logger = logging.getLogger(__name__)

#: Dagster statuses meaning a run has not finished — another must not be launched beside it.
IN_FLIGHT_STATUSES = frozenset({"QUEUED", "NOT_STARTED", "STARTING", "STARTED", "CANCELING"})

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
    """Today's snapshot coverage when it is below par (0.0 when nothing was captured),
    else None. The sensor treats any non-None as "capture now".

    Deliberately today-only. Option chains are live-only — re-running tomorrow snapshots
    tomorrow's chains, so a missed past day is a permanent hole. But *today* is always
    salvageable while the market has closed, whether the snapshot is **missing** (the
    19:00 schedule never fired because the stack was down) or **thin** (a run was
    interrupted). `snapshot_option_chains` commits per ticker and upserts on
    (snapshot_date, ticker, ...), so a re-run fills whatever is absent.

    A missing snapshot counts as a gap (coverage 0.0) rather than "not our job" — that is
    the whole point of surviving stack up/down: if you are up any time post-close on a
    trading day, today's snapshot gets taken. Callers gate on `is_post_close()`, so this
    is only ever consulted after the close.
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
    if not universe_size:
        return None  # market not configured for this exchange — nothing to capture
    coverage = covered / universe_size
    return coverage if coverage < MIN_COVERAGE else None


def summarize_capture_runs(runs: Iterable[tuple[str, float | None]]) -> tuple[bool, int]:
    """From `(status, start_time)` pairs, return `(in_flight, reached_feed)`.

    `reached_feed` counts only runs that actually began executing. Dagster sets
    `start_time` when a run leaves the queue, so a run cancelled *while still queued* has
    `start_time is None` and never touched the vendor — it must not consume the daily
    budget. That is exactly what went wrong on 2026-07-23: three pre-market runs were
    cancelled before executing, yet they exhausted the budget and locked the sensor out
    for the whole evening, so the post-close capture fell to the schedule instead.
    """
    in_flight = False
    reached_feed = 0
    for status, start_time in runs:
        if status in IN_FLIGHT_STATUSES:
            in_flight = True
        if start_time is not None:
            reached_feed += 1
    return in_flight, reached_feed
