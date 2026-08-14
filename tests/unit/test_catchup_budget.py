"""A session is only *missed* once its scheduled ingest is overdue, and rescue attempts
must never reuse a run_key.

Regression: at 00:08 ET the exchange date flipped and the catch-up sensor
requested that day's partition ~18 hours before its scheduled ingest — a run against a
session that had not opened. Worse, the fixed `catchup-{exchange}-{day}` run_key was
thereby consumed forever (Dagster dedupes sensor run_keys permanently), so had the
evening schedule also been missed, the day would have been silently unrescuable.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from quantpulse.orchestration.catchup import (
    MAX_INGEST_ATTEMPTS_PER_SESSION,
    exchange_day_start_utc,
    ingest_overdue,
    next_ingest_attempt,
)

ET = ZoneInfo("America/New_York")
SAST = ZoneInfo("Africa/Johannesburg")

# Fixed run-history pairs, as summarize_capture_runs sees them.
QUEUED_THEN_CANCELLED = ("CANCELED", None)
SUCCEEDED = ("SUCCESS", 1_000.0)
FAILED = ("FAILURE", 1_000.0)
STILL_QUEUED = ("QUEUED", None)


# --- ingest_overdue: when does today become an expected session? ---


def test_midnight_is_not_overdue() -> None:
    """The firing moment this guards: date flipped, session ~18h away."""
    assert not ingest_overdue(dt.datetime(2026, 7, 24, 0, 8, tzinfo=ET), "XNYS")


def test_post_close_but_pre_schedule_is_not_overdue() -> None:
    """Between close and the scheduled ingest the schedule still owns the session —
    a rescue here would just duplicate its vendor calls."""
    assert not ingest_overdue(dt.datetime(2026, 7, 24, 17, 0, tzinfo=ET), "XNYS")


def test_overdue_exactly_at_the_scheduled_minute() -> None:
    assert not ingest_overdue(dt.datetime(2026, 7, 24, 18, 29, tzinfo=ET), "XNYS")
    assert ingest_overdue(dt.datetime(2026, 7, 24, 18, 30, tzinfo=ET), "XNYS")


def test_jse_overdue_uses_its_own_clock() -> None:
    """19:30 SAST is the JSE's ingest time — 13:30 ET, hours before the NYSE one."""
    when = dt.datetime(2026, 7, 24, 19, 30, tzinfo=SAST)
    assert ingest_overdue(when, "XJSE")
    assert ingest_overdue(when.astimezone(ET), "XJSE")  # tz-normalized, same instant
    assert not ingest_overdue(when, "XNYS")


# --- next_ingest_attempt: fresh run_key or stand down ---


def test_clean_slate_starts_at_attempt_one() -> None:
    assert next_ingest_attempt([]) == 1


def test_in_flight_run_blocks_a_second_request() -> None:
    assert next_ingest_attempt([STILL_QUEUED]) is None


def test_budget_counts_only_runs_that_reached_the_feed() -> None:
    """Cancelled-in-queue runs never touched the vendor: no budget spent, but the
    attempt number still advances past them so the run_key is fresh."""
    assert next_ingest_attempt([QUEUED_THEN_CANCELLED] * 3) == 4


def test_spent_budget_stands_down() -> None:
    executed = [FAILED] * MAX_INGEST_ATTEMPTS_PER_SESSION
    assert next_ingest_attempt(executed) is None


def test_attempt_numbers_never_collide_with_history() -> None:
    """One premature success + one failure -> the next key must be the third."""
    assert next_ingest_attempt([SUCCEEDED, FAILED]) == 3


# --- the budget must expire ---
#
# A 24-hour internet outage failed four ingests per market. The budget counted every run
# ever recorded for the partition, so when connectivity returned the sensor stood down
# permanently and both sessions had to be backfilled by hand. Three attempts is a ceiling
# on a feed that is down *today*; a permanent one is giving up.


def test_yesterdays_exhausted_budget_does_not_block_today() -> None:
    """The case this guards: four failed runs yesterday, none today."""
    yesterday = [FAILED] * 4
    assert next_ingest_attempt(yesterday, todays_runs=[]) == 5


def test_todays_budget_still_stops_a_dead_feed() -> None:
    """The protection the ceiling exists for is unchanged within a day."""
    todays = [FAILED] * MAX_INGEST_ATTEMPTS_PER_SESSION
    assert next_ingest_attempt(todays + [FAILED] * 4, todays_runs=todays) is None


def test_the_attempt_number_counts_every_run_ever_not_just_today() -> None:
    """Budget and run_key answer different questions. A run_key is deduplicated forever,
    so numbering from today's runs alone would reissue yesterday's key and the request
    would silently vanish — the same bug as the fixed key this replaced."""
    history = [FAILED] * 4  # yesterday
    assert next_ingest_attempt(history, todays_runs=[]) == 5  # not 1


def test_an_in_flight_run_today_still_blocks() -> None:
    assert next_ingest_attempt([FAILED] * 9, todays_runs=[STILL_QUEUED]) is None


def test_omitting_todays_runs_falls_back_to_the_whole_history() -> None:
    """Back-compatible default: callers that do not scope a window get the old behaviour
    rather than an unbounded retry loop."""
    assert next_ingest_attempt([FAILED] * MAX_INGEST_ATTEMPTS_PER_SESSION) is None


# --- the "today" boundary must be UTC ---
#
# The budget above is only as good as the window it counts over. Dagster's
# RunsFilter(created_after=...) compares wall-clock fields against the naive-UTC
# create_timestamp column and IGNORES tzinfo, so an aware local datetime silently moves the
# boundary by the offset. Measured live: 00:00+02:00 matched 3 runs where 22:00Z matched 10,
# so the JSE catch-up made 10 attempts against a ceiling of 3.


def test_boundary_is_expressed_in_utc() -> None:
    """What Dagster compares is the wall clock, so the wall clock has to already be UTC."""
    start = exchange_day_start_utc(dt.date(2026, 8, 13), "XJSE")
    assert start.utcoffset() == dt.timedelta(0)
    # The naive value Dagster actually reads, not merely an equivalent instant.
    assert start.replace(tzinfo=None) == dt.datetime(2026, 8, 12, 22, 0)


def test_boundary_is_still_the_exchange_midnight() -> None:
    """Converting must not move the instant — only how it is spelled."""
    for exchange, tz in (("XJSE", SAST), ("XNYS", ET)):
        day = dt.date(2026, 8, 13)
        assert exchange_day_start_utc(day, exchange) == dt.datetime.combine(
            day, dt.time.min, tzinfo=tz
        )


def test_each_market_gets_its_own_midnight_and_they_differ() -> None:
    """The skew ran opposite ways per market — JSE's window opened 2h late (budget too
    loose), NYSE's 4h early (too strict, and on option captures that cannot be refetched).
    A single shared boundary would be wrong for at least one of them."""
    day = dt.date(2026, 8, 13)
    jse = exchange_day_start_utc(day, "XJSE").replace(tzinfo=None)
    nyse = exchange_day_start_utc(day, "XNYS").replace(tzinfo=None)
    assert jse == dt.datetime(2026, 8, 12, 22, 0)  # SAST is UTC+2
    assert nyse == dt.datetime(2026, 8, 13, 4, 0)  # EDT is UTC-4
    assert jse < nyse


# --- the boundary has to follow DST, not a fixed offset ---
#
# Every test above dates from August, when New York is UTC-4. A fixed-offset implementation
# is indistinguishable from a correct one in EDT, so all of them pass against hardcoded
# offsets — verified by trying it. The bug appears on the first session after the clocks go
# back, when the catch-up budget counts over a window shifted by an hour and the sensor
# misjudges which runs were "today".

WINTER = dt.date(2026, 11, 2)  # first XNYS session under EST
SUMMER = dt.date(2026, 8, 13)  # EDT


def test_the_boundary_follows_dst_rather_than_a_fixed_offset() -> None:
    """Midnight ET is 04:00Z in summer and 05:00Z in winter. Pinning both sides is the
    only way this file can tell a tz lookup from an arithmetic shortcut."""
    assert exchange_day_start_utc(SUMMER, "XNYS").replace(tzinfo=None) == dt.datetime(
        2026, 8, 13, 4, 0
    )
    assert exchange_day_start_utc(WINTER, "XNYS").replace(tzinfo=None) == dt.datetime(
        2026, 11, 2, 5, 0
    )


def test_the_jse_boundary_does_not_move_across_the_us_transition() -> None:
    """South Africa has never observed DST, so SAST is UTC+2 year round. A shared 'shift
    the clocks' fudge applied to both markets would break this one."""
    for day in (SUMMER, WINTER):
        start = exchange_day_start_utc(day, "XJSE").replace(tzinfo=None)
        assert start == dt.datetime.combine(day - dt.timedelta(days=1), dt.time(22, 0))


def test_the_gap_between_the_two_markets_changes_with_us_dst() -> None:
    """The markets are 6 hours apart in the northern summer and 7 in winter. Anything
    that assumes a constant inter-market offset is wrong for half the year."""
    summer_gap = exchange_day_start_utc(SUMMER, "XNYS") - exchange_day_start_utc(SUMMER, "XJSE")
    winter_gap = exchange_day_start_utc(WINTER, "XNYS") - exchange_day_start_utc(WINTER, "XJSE")
    assert summer_gap == dt.timedelta(hours=6)
    assert winter_gap == dt.timedelta(hours=7)
