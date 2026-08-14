"""Detect trading days the pipeline slept through.

Schedules only fire while the stack is up, and this runs on a laptop. Compare each
exchange's expected sessions against what actually landed in `prices` so the catch-up
sensor can request the gaps.
"""

import datetime as dt
import logging
from collections.abc import Iterable

from sqlalchemy import text

# Re-exported: is_post_close became exchange-aware and now lives with the registry, but
# the sensors import it from here.
from quantpulse.data.calendar import (
    DEFAULT_EXCHANGE,
    get_exchange,
    is_post_close,  # noqa: F401
)
from quantpulse.db import get_engine

logger = logging.getLogger(__name__)

#: Dagster statuses meaning a run has not finished — another must not be launched beside it.
IN_FLIGHT_STATUSES = frozenset({"QUEUED", "NOT_STARTED", "STARTING", "STARTED", "CANCELING"})

# A session counts as ingested only if a healthy share of the universe arrived; a
# partially-written day should be retried, not treated as done.
MIN_COVERAGE = 0.8

# When each market's scheduled ingest fires: close + this many hours, at this minute.
# Lives here (not in definitions.py) because "has the schedule had its turn yet" is part
# of deciding whether a session is *missed* — the cron in definitions imports these.
INGEST_HOUR_AFTER_CLOSE = 2
INGEST_MINUTE = 30

# A broken feed must not be retried every sensor tick all day; failures are already
# reported by the run-failure sensor.
MAX_INGEST_ATTEMPTS_PER_SESSION = 3

# How many of the newest ingested sessions stay eligible for a benchmark-only re-ingest.
# Bounds the cost when a bar is never published: eligibility expires rather than retrying
# for the whole lookback. Five sessions is about a week of chances, which is ample for a
# bar that arrives a day or two late.
BENCHMARK_RETRY_SESSIONS = 5


def ingest_overdue(now: dt.datetime | None = None, exchange: str = DEFAULT_EXCHANGE) -> bool:
    """Has today's *scheduled* ingest time already passed, in exchange time?

    Until then today's session is not "missed" — the schedule has not had its turn. The
    exchange's calendar date flips at midnight, hours before trading starts, so treating
    the new date as an expected session requests a run against a session that has not
    opened: it fetches nothing and spends one of the day's rescue attempts.
    """
    ex = get_exchange(exchange)
    now = now or dt.datetime.now(ex.tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ex.tz)
    local = now.astimezone(ex.tz)
    # Both registered markets close mid-afternoon, so close + 2h is always the same
    # local day; a market whose ingest crossed midnight would need date math here.
    due = dt.time(ex.close_hour + INGEST_HOUR_AFTER_CLOSE, INGEST_MINUTE)
    return local.time() >= due


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


def benchmark_gaps_to_retry(
    ingested: Iterable[dt.date],
    benchmark_dates: Iterable[dt.date],
    limit: int = BENCHMARK_RETRY_SESSIONS,
) -> list[dt.date]:
    """Which recently-ingested sessions are missing their benchmark bar, oldest first.

    Split from the query below so the window arithmetic is unit-testable without a
    database.

    Only the newest `limit` ingested sessions are eligible. A coverage-triggered retry is
    self-limiting, because a re-ingest that works fixes the coverage that asked for it.
    This one is not: the vendor may never publish the bar, and without a bound a single
    absent bar would re-ingest its session every day for the whole lookback. The freshness
    asset check keeps reporting the gap regardless — reporting is cheap, retrying is not.
    """
    have = set(benchmark_dates)
    recent = sorted(set(ingested))[-limit:] if limit > 0 else []
    return [day for day in recent if day not in have]


def benchmark_missing_days(
    expected: list[dt.date], exchange: str = DEFAULT_EXCHANGE
) -> list[dt.date]:
    """Sessions worth re-ingesting solely because the market's benchmark bar is absent.

    Coverage cannot see this. The benchmark is one ticker, so losing it barely moves the
    coverage ratio and the day is judged complete — but `fct_alpha_beta` and
    `fct_portfolio_vs_benchmark` inner-join it, so its absence drops the whole day from
    them while the track record keeps it.

    Considers only sessions the market actually ingested. A day with no data at all belongs
    to `missing_trading_days`; requesting it here as well would spend the session's retry
    budget twice over for one cause.

    Safe to retry because the ingest job is partitioned by single date: for a ticker with a
    genuine hole, a one-day window returns nothing rather than a neighbouring bar.
    """
    if not expected:
        return []
    benchmark = get_exchange(exchange).benchmark
    start, end = min(expected), max(expected)
    with get_engine().connect() as conn:
        ingested = conn.execute(
            text(
                "SELECT p.date FROM prices p "
                "JOIN universe u ON u.ticker = p.ticker AND u.exchange = :ex "
                "WHERE p.date >= :start AND p.date <= :end GROUP BY p.date"
            ),
            {"start": start, "end": end, "ex": exchange},
        ).all()
        covered = conn.execute(
            text("SELECT date FROM prices WHERE ticker = :t AND date >= :start AND date <= :end"),
            {"t": benchmark, "start": start, "end": end},
        ).all()
    expected_set = set(expected)
    missing = benchmark_gaps_to_retry(
        [r.date for r in ingested if r.date in expected_set], [r.date for r in covered]
    )
    if missing:
        logger.info("Catch-up: %s missing its benchmark %s on %s", exchange, benchmark, missing[:5])
    return missing


def option_snapshot_incomplete(today: dt.date, exchange: str = DEFAULT_EXCHANGE) -> float | None:
    """Today's snapshot coverage when it is below par (0.0 when nothing was captured),
    else None. The sensor treats any non-None as "capture now".

    Deliberately today-only. Option chains are live-only, so re-running tomorrow captures
    tomorrow's chains and a missed past day is a permanent hole. Today stays salvageable
    once the market has closed, whether the snapshot is missing (the stack was down when
    the schedule fired) or thin (a run was interrupted): the capture commits and upserts
    per ticker, so a re-run fills whatever is absent.

    A missing snapshot counts as a gap rather than "not our job" — if the stack is up at
    any point post-close on a trading day, today's snapshot gets taken. Callers gate on
    `is_post_close()`.
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
    `start_time` when a run leaves the queue, so a run cancelled while still queued never
    touched the vendor and must not spend the daily budget — otherwise a handful of
    queued-then-cancelled runs can lock the sensor out for a whole evening.

    Shared by both rescue sensors: option capture directly, ingest catch-up via
    `next_ingest_attempt`.
    """
    in_flight = False
    reached_feed = 0
    for status, start_time in runs:
        if status in IN_FLIGHT_STATUSES:
            in_flight = True
        if start_time is not None:
            reached_feed += 1
    return in_flight, reached_feed


def exchange_day_start_utc(day: dt.date, exchange: str = DEFAULT_EXCHANGE) -> dt.datetime:
    """Midnight in the exchange's timezone, expressed in UTC, for `RunsFilter`.

    Dagster's `created_after` compares wall-clock fields against the naive-UTC
    `create_timestamp` column and ignores `tzinfo`, so an aware local datetime silently
    moves the boundary by the UTC offset — and in opposite directions for markets either
    side of UTC. Either way the daily budget is counted over the wrong window: too loose on
    one market, too tight on the other. Converting first makes the wall-clock fields the
    ones Dagster actually compares.
    """
    return dt.datetime.combine(day, dt.time.min, tzinfo=get_exchange(exchange).tz).astimezone(
        dt.UTC
    )


def next_ingest_attempt(
    runs: list[tuple[str, float | None]],
    todays_runs: list[tuple[str, float | None]] | None = None,
) -> int | None:
    """Attempt number for another catch-up ingest of a session, or None when one is in
    flight or **today's** budget for it is spent.

    Two questions, deliberately answered from two different lists.

    `todays_runs` decides *whether* to retry. The budget has to expire daily, or a session
    that burns its attempts during an outage can never recover automatically once the cause
    is fixed. Three attempts is a sane ceiling for a feed that is down today; a permanent
    one is giving up.

    `runs` — every attempt ever — decides *what to call it*. The number suffixes the
    Dagster run_key and a run_key is deduplicated **forever**, so the counter has to stay
    monotonic across days. Reusing yesterday's key makes today's request silently vanish.
    """
    today = runs if todays_runs is None else todays_runs
    in_flight, reached_feed = summarize_capture_runs(today)
    if in_flight or reached_feed >= MAX_INGEST_ATTEMPTS_PER_SESSION:
        return None
    return len(runs) + 1
