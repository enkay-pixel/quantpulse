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
    session_in_progress,
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

# When the cross-market process schedule fires. Features rank within each exchange and books
# build per market, so processing runs ONCE for both markets after the latest close of the
# day — the NYSE's. Here for the same reason the ingest constants are: whether features are
# owed yet is a question about this schedule, and definitions.py imports these for its cron.
PROCESS_HOUR = 19
PROCESS_MINUTE = 0
PROCESS_TIMEZONE = "America/New_York"

# A broken feed must not be retried every sensor tick all day; failures are already
# reported by the run-failure sensor.
MAX_INGEST_ATTEMPTS_PER_SESSION = 3

# How many of the newest ingested sessions stay eligible for a re-ingest that fills missing
# tickers. Bounds the cost when a bar is never published: eligibility expires rather than
# retrying for the whole lookback. Five sessions is about a week of chances, which is ample
# for a bar that arrives a day or two late.
TICKER_GAP_RETRY_SESSIONS = 5

#: Run tag marking a re-ingest that may only add the bars a session is missing. A session
#: that is already partly stored keeps every bar it has: re-fetching it would rewrite those
#: with whatever the vendor serves now, which after a corporate action is a differently
#: adjusted price sitting between unadjusted neighbours.
FILL_ONLY_TAG = "quantpulse/fill_only"


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


def process_overdue(day: dt.date, now: dt.datetime | None = None) -> bool:
    """Has the cross-market process schedule's slot for `day` already passed?

    Prices and features are owed at different times, and by different clocks. Ingest fires
    per market on that market's own close; processing fires once for both markets at
    `PROCESS_HOUR` New York. An earlier-closing market therefore holds prices for hours
    before it can hold features, entirely correctly — on the JSE, ingest lands at 17:30 SAST
    and processing does not run until 01:00 SAST the next morning.

    A checker that expects both the moment ingest lands reports a stall for those hours every
    weekday. That is what happened on 2026-09-01: features sat a day behind prices,
    `check-daily-pipeline` and a second health check both called it stalled, and the run they
    were waiting for succeeded on time at 23:00 UTC that night.

    Judged in exchange-independent New York time, because the schedule is: `day` is the
    trading date being asked about, and the JSE session on `day` closes the same New York
    calendar day it opened.
    """
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(PROCESS_TIMEZONE)
    now = now.astimezone(tz) if now else dt.datetime.now(tz)
    due = dt.datetime.combine(day, dt.time(PROCESS_HOUR, PROCESS_MINUTE), tzinfo=tz)
    return now >= due


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
        universe_size: int = conn.execute(
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


def ticker_gaps_to_retry(
    ingested: Iterable[dt.date],
    gap_days: Iterable[dt.date],
    trained_through: dt.date | None,
    limit: int = TICKER_GAP_RETRY_SESSIONS,
) -> list[dt.date]:
    """Which recently-ingested sessions are missing tickers and may still be filled, oldest
    first.

    Split from the query below so the window arithmetic is unit-testable without a database.

    Only the newest `limit` ingested sessions are eligible. A coverage-triggered retry is
    self-limiting, because a re-ingest that works fixes the coverage that asked for it. This
    one is not: the vendor may never publish a bar, and without a bound a single absent bar
    would re-ingest its session every day for the whole lookback. The post-close check keeps
    reporting the gap regardless — reporting is cheap, retrying is not.

    And no session a training run has already used. A retrain records what it was fitted
    on, and anything that refits it later to check it — the shadow scorer does every week —
    needs that data unchanged; filling a gap after the fact turns a reproducible model into
    one that can no longer be rebuilt. `trained_through` is the date of the newest training
    run in exchange time, and a session on or before it counts as used.
    """
    gaps = set(gap_days)
    recent = sorted(set(ingested))[-limit:] if limit > 0 else []
    return [
        day for day in recent if day in gaps and (trained_through is None or day > trained_through)
    ]


def latest_training_day(exchange: str = DEFAULT_EXCHANGE) -> dt.date | None:
    """The newest session this market's newest training run could have used, or None.

    That is the newest session with a bar stored before the run was created, the panel
    `build_dataset(known_by=...)` reloads, and not the run's own date. A drift retrain is created
    at 01:05 SAST, after midnight in Johannesburg and London. Dated by its creation, it claimed a
    session that had not traded yet, and so blocked that session's fill-only retry: London's
    2026-10-22 kept seven missing bars the vendor had (docs/findings/partial-cross-sections.md).
    """
    with get_engine().connect() as conn:
        used: dt.date | None = conn.execute(
            text(
                "SELECT max(p.date) FROM prices p "
                "JOIN universe u ON u.ticker = p.ticker AND u.exchange = :ex "
                "WHERE p.ingested_at <= (SELECT max(created_at) FROM model_runs "
                "WHERE run_type = 'train' AND exchange = :ex)"
            ),
            {"ex": exchange},
        ).scalar_one()
    return used


#: How many times a market's newest scored session may be re-scored for bars that arrived after
#: its processing run. Late bars come in batches (New York's 2026-10-23 arrived in four), and a
#: listing whose features cannot be computed yet must not ask again on every tick.
MAX_RESCORES_PER_SESSION = 3

#: Run tags on a re-score: which market and session it is for, and how many late listings it was
#: requested to score.
RESCORE_TAG = "quantpulse/rescore"
UNSCORED_TAG = "quantpulse/unscored"

# Active listings with a bar on the session and no prediction for it. With :late, only those
# whose bar was stored after the session was first scored: the ones a second pass can still
# reach, since a listing that was unscorable at the first pass stays so.
_UNSCORED_LISTINGS = """
    SELECT u.ticker FROM universe u
    JOIN prices p ON p.ticker = u.ticker AND p.date = :day
    WHERE u.exchange = :ex AND u.active
      AND NOT EXISTS (SELECT 1 FROM predictions pr WHERE pr.ticker = u.ticker AND pr.date = :day)
      AND (NOT :late OR p.ingested_at > (
          SELECT min(pr.created_at) FROM predictions pr
          JOIN universe pu ON pu.ticker = pr.ticker AND pu.exchange = :ex
          WHERE pr.date = :day))
    ORDER BY u.ticker
"""


def newest_scored_session(exchange: str = DEFAULT_EXCHANGE) -> dt.date | None:
    """The newest session this market has any prediction for."""
    with get_engine().connect() as conn:
        day: dt.date | None = conn.execute(
            text(
                "SELECT max(p.date) FROM predictions p "
                "JOIN universe u ON u.ticker = p.ticker AND u.exchange = :ex"
            ),
            {"ex": exchange},
        ).scalar_one()
    return day


def unscored_listings(
    day: dt.date, exchange: str = DEFAULT_EXCHANGE, late: bool = False
) -> list[str]:
    """Listings that had a bar on `day` but were never scored for it.

    Scoring fills dates with no predictions at all and re-scores only the newest one, so a name
    whose bar landed after its session was scored stays unscored: New York's 2026-10-23 was
    scored on 33 of 50. `late` keeps only the bars stored after that first scoring.
    """
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(_UNSCORED_LISTINGS), {"ex": exchange, "day": day, "late": late}
        ).all()
    return [r.ticker for r in rows]


def rescore_candidate(exchange: str = DEFAULT_EXCHANGE) -> tuple[dt.date, list[str]] | None:
    """The newest scored session and its late, unscored listings, if a second pass can fix them.

    Two conditions keep a re-score from changing anything already published:
    - **The session is still the market's newest.** Once the next session's bars are stored, the
      nightly run scores that one, and the newest-date re-score no longer reaches this date.
    - **Its book row does not exist yet.** A book row for a date is written once the next
      session's return is known. After that, adding names would rewrite a published book.
    """
    day = newest_scored_session(exchange)
    if day is None:
        return None
    with get_engine().connect() as conn:
        newest_bar: dt.date | None = conn.execute(
            text(
                "SELECT max(p.date) FROM prices p "
                "JOIN universe u ON u.ticker = p.ticker AND u.exchange = :ex"
            ),
            {"ex": exchange},
        ).scalar_one()
        booked: dt.date | None = conn.execute(
            text("SELECT max(date) FROM portfolio_snapshots WHERE exchange = :ex"),
            {"ex": exchange},
        ).scalar_one()
    if newest_bar is not None and newest_bar > day:
        return None
    if booked is not None and booked >= day:
        return None
    late = unscored_listings(day, exchange, late=True)
    return (day, late) if late else None


def rescore_attempt(unscored: int, runs: Iterable[tuple[str, str | None]]) -> int | None:
    """Which re-score attempt to request for a session, or None to wait or stop.

    `runs` holds each earlier re-score of that session as (Dagster status, the unscored count it
    was requested for). Wait while one is in flight. Stop once one has succeeded with the same
    count, since another pass would score nothing new: that is a listing whose features cannot be
    computed yet, which would otherwise ask again every tick. And stop at
    MAX_RESCORES_PER_SESSION, the bound every "re-run until X appears" trigger here carries.
    """
    if unscored <= 0:
        return None
    earlier = list(runs)
    if any(status in IN_FLIGHT_STATUSES for status, _ in earlier):
        return None
    if any(status == "SUCCESS" and count == str(unscored) for status, count in earlier):
        return None
    if len(earlier) >= MAX_RESCORES_PER_SESSION:
        return None
    return len(earlier) + 1


#: Active tickers absent on a session they were already trading before it. A ticker with no
#: earlier bar is a new listing rather than a gap.
_MISSING_TICKERS = """
    SELECT u.ticker FROM universe u
    WHERE u.exchange = :ex AND u.active
      AND NOT EXISTS (SELECT 1 FROM prices p WHERE p.ticker = u.ticker AND p.date = :day)
      AND EXISTS (SELECT 1 FROM prices p WHERE p.ticker = u.ticker AND p.date < :day)
    ORDER BY u.ticker
"""


def missing_tickers(day: dt.date, exchange: str = DEFAULT_EXCHANGE) -> list[str]:
    """The tickers a stored session is missing — what a fill-only re-ingest fetches."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(_MISSING_TICKERS), {"ex": exchange, "day": day}).all()
    return [r.ticker for r in rows]


def ticker_gap_days(expected: list[dt.date], exchange: str = DEFAULT_EXCHANGE) -> list[dt.date]:
    """Sessions worth re-ingesting because some of their tickers are absent.

    Coverage cannot see this. A session counts as ingested once the floor share of the
    universe has arrived, and the scheduled ingest fetches only its own day, so the tickers
    that did not arrive are never asked for again. That costs more than the missing rows:
    features and labels shift by row, so a missing day stretches those tickers' returns
    across the gap. The market's benchmark is one such ticker, and its absence also drops
    the whole day from the marts that join on it.

    Considers only sessions the market actually ingested. A day with no data at all belongs
    to `missing_trading_days`; requesting it here as well would spend the session's retry
    budget twice over for one cause.
    """
    if not expected:
        return []
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
        expected_set = set(expected)
        days = [r.date for r in ingested if r.date in expected_set]
        gap_days = [
            day
            for day in days
            if conn.execute(text(_MISSING_TICKERS), {"ex": exchange, "day": day}).first()
        ]
    missing = ticker_gaps_to_retry(days, gap_days, latest_training_day(exchange))
    if missing:
        logger.info("Catch-up: %s sessions missing tickers: %s", exchange, missing[:5])
    return missing


def fetch_would_end_in_open_session(
    day: dt.date, now: dt.datetime | None = None, exchange: str = DEFAULT_EXCHANGE
) -> bool:
    """Would a one-day ingest of `day` ask the vendor for a session still trading?

    The vendor's end bound is exclusive, so a one-day request for `day` runs to `day + 1`.
    When that is today and today's session is open, the vendor can return the session in
    progress labelled as `day` — today's price under yesterday's date, the misdating the
    data dictionary records. Wait for the close; every other day is safe.
    """
    ex = get_exchange(exchange)
    now = now or dt.datetime.now(ex.tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ex.tz)
    today = now.astimezone(ex.tz).date()
    return day + dt.timedelta(days=1) == today and session_in_progress(now, exchange)


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
        universe_size: int = conn.execute(
            text("SELECT count(*) FROM universe WHERE active AND exchange = :ex"),
            {"ex": exchange},
        ).scalar_one()
        covered: int = conn.execute(
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


# --- the drift retrain ----------------------------------------------------------------------

#: The run_key the drift retrain sensor gives each request, which names the drift day it was for.
DRIFT_RUN_KEY_PREFIX = "drift-retrain-"


def drift_retrain_due(
    drift_days: Iterable[tuple[dt.date, bool]],
    last_retrain_day: dt.date | None,
    promoted_since: bool,
) -> tuple[bool, str]:
    """Whether a market's drift warrants an off-cycle retrain now, and why.

    A drift retrain is tried once per drift episode per champion. Drift is measured against the
    champion's training data, which a rejected candidate does not change, so a market that keeps
    drifting keeps firing the trigger on the same evidence, and each refit sees a panel all but
    identical to the one just rejected: London was refitted on three consecutive days of an
    unchanged 0.308 share, every candidate rejected. Like every "re-run until X appears" trigger
    here, it needs a bound. It fires again once the champion changes, or once the drift has
    cleared and returned; the scheduled weekly retrain runs regardless.

    `drift_days` is the market's drift checks, one per session, newest first; `last_retrain_day`
    the drift day the market's latest successful drift retrain was fired for; `promoted_since`
    whether any candidate was promoted for the market after that retrain.
    """
    days = list(drift_days)
    if not days or not days[0][1]:
        return False, "no drift beyond threshold"
    episode_start = days[0][0]
    for day, drifted in days:
        if not drifted:
            break
        episode_start = day
    if last_retrain_day is not None and last_retrain_day >= episode_start and not promoted_since:
        return False, (
            f"drifting since {episode_start}, already retrained for it ({last_retrain_day}) "
            "and the champion has not changed"
        )
    return True, f"drifting since {episode_start}"


def drift_day_of(run_key: str | None, exchange: str) -> dt.date | None:
    """The drift day a drift retrain's run_key names (`drift-retrain-XLON-2026-10-19`)."""
    prefix = f"{DRIFT_RUN_KEY_PREFIX}{exchange}-"
    if not run_key or not run_key.startswith(prefix):
        return None
    try:
        return dt.date.fromisoformat(run_key[len(prefix) :])
    except ValueError:
        return None


def promoted_after(exchange: str, since: dt.datetime) -> bool:
    """Whether a candidate was promoted for the market after `since`."""
    with get_engine().connect() as conn:
        return bool(
            conn.execute(
                text(
                    "SELECT 1 FROM model_runs WHERE exchange = :ex AND run_type = 'train' "
                    "AND decision = 'promoted' AND created_at > :since LIMIT 1"
                ),
                {"ex": exchange, "since": since},
            ).first()
        )
