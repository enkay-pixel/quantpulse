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

# A genuinely broken feed must not be hammered every sensor tick all day; failures are
# already loud via the run-failure sensor. Same shape as MAX_OPTION_REPAIRS_PER_DAY.
MAX_INGEST_ATTEMPTS_PER_SESSION = 3


def ingest_overdue(now: dt.datetime | None = None, exchange: str = DEFAULT_EXCHANGE) -> bool:
    """Has today's *scheduled* ingest time already passed, in exchange time?

    Until that moment today's session is not "missed" — the schedule simply hasn't had
    its turn. The exchange's calendar date flips at its midnight, hours before trading
    starts, so treating the new date as an expected session made the catch-up sensor
    request 2026-07-24|XNYS at 00:08 ET: a run against a session that had not opened,
    which fetched nothing and consumed that day's only rescue attempt (see
    `next_ingest_attempt` for the other half of that incident).
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

    Shared by both rescue sensors: option-capture directly, ingest catch-up via
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

    Dagster's `created_after` compares **wall-clock fields** against the naive-UTC
    `create_timestamp` column and ignores `tzinfo` entirely, so handing it an aware local
    datetime silently moves the boundary by the UTC offset — in the wrong direction, and
    differently per market. Measured on the live instance for `2026-08-12|XJSE`:

        created_after=2026-08-13 00:00+02:00  ->  3 runs   (boundary lands at 02:00 SAST)
        created_after=2026-08-12 22:00+00:00  -> 10 runs   (correct)

    Under-counting made the JSE catch-up budget far too generous — 10 attempts in a night
    against a ceiling of 3. For XNYS the same mistake goes the other way: 00:00 EDT read as
    00:00 UTC starts the window at 20:00 the previous evening, so yesterday's late option
    captures count against today's budget and can block a capture that cannot be refetched.

    Converting first makes the wall-clock fields the ones Dagster is actually comparing.
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

    Two different questions, deliberately answered from two different lists:

    `todays_runs` decides *whether* to retry. The budget must expire, or a session that
    burns its attempts during an outage can never be recovered automatically even after the
    cause is fixed. That happened on 2026-08-11: a 24-hour internet outage failed four
    ingests per market, the budget counted every run ever recorded for the partition, and
    when connectivity returned the sensor stood down permanently — both sessions had to be
    backfilled by hand. Three attempts is a sane daily ceiling on a feed that is genuinely
    down; a permanent one is just giving up.

    `runs` — every attempt ever — decides *what to call it*. The number suffixes the
    Dagster run_key and a run_key is deduplicated **forever**, so the counter has to stay
    monotonic across days. Reusing yesterday's key makes today's request silently vanish,
    which is the same class of bug as the original fixed key it replaced.
    """
    today = runs if todays_runs is None else todays_runs
    in_flight, reached_feed = summarize_capture_runs(today)
    if in_flight or reached_feed >= MAX_INGEST_ATTEMPTS_PER_SESSION:
        return None
    return len(runs) + 1
