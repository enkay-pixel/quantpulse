"""A session is only *missed* once its scheduled ingest is overdue, and rescue attempts
must never reuse a run_key.

Regression (2026-07-24): at 00:08 ET the exchange date flipped and the catch-up sensor
requested that day's partition ~18 hours before its scheduled ingest — a run against a
session that had not opened. Worse, the fixed `catchup-{exchange}-{day}` run_key was
thereby consumed forever (Dagster dedupes sensor run_keys permanently), so had the
evening schedule also been missed, the day would have been silently unrescuable.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from quantpulse.orchestration.catchup import (
    MAX_INGEST_ATTEMPTS_PER_SESSION,
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
    """The exact 2026-07-24 firing moment: date flipped, session ~18h away."""
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


# --- the budget must expire (2026-08-11) ---
#
# A 24-hour internet outage failed four ingests per market. The budget counted every run
# ever recorded for the partition, so when connectivity returned the sensor stood down
# permanently and both sessions had to be backfilled by hand. Three attempts is a ceiling
# on a feed that is down *today*; a permanent one is giving up.


def test_yesterdays_exhausted_budget_does_not_block_today() -> None:
    """The exact 2026-08-11 case: four failed runs yesterday, none today."""
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
