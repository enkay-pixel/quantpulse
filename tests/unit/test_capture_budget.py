"""The daily capture budget must count runs that reached the vendor, not runs requested.

Regression: on 2026-07-23 three pre-market capture runs were cancelled while still queued.
They never touched the feed, yet the old cursor counted them as attempts, exhausting the
budget and locking the sensor out for the entire evening — the post-close snapshot only
landed because the 19:00 schedule caught it.
"""

from quantpulse.orchestration.catchup import summarize_capture_runs

# Dagster sets start_time when a run leaves the queue and begins executing.
QUEUED_THEN_CANCELLED = ("CANCELED", None)
RAN_THEN_CANCELLED = ("CANCELED", 1_000.0)
SUCCEEDED = ("SUCCESS", 1_000.0)
FAILED = ("FAILURE", 1_000.0)
STILL_QUEUED = ("QUEUED", None)
RUNNING = ("STARTED", 1_000.0)


def test_runs_cancelled_before_executing_do_not_consume_budget() -> None:
    """The exact 2026-07-23 case: three cancelled-while-queued runs, budget untouched."""
    in_flight, reached = summarize_capture_runs([QUEUED_THEN_CANCELLED] * 3)
    assert reached == 0
    assert not in_flight


def test_runs_that_executed_do_consume_budget() -> None:
    """A run that reached the vendor counts, however it ended — that is the point of the
    cap: a genuinely broken feed must not be retried all evening."""
    _, reached = summarize_capture_runs([SUCCEEDED, FAILED, RAN_THEN_CANCELLED])
    assert reached == 3


def test_a_queued_or_running_capture_is_in_flight() -> None:
    """Never launch a second capture beside one that has not finished."""
    assert summarize_capture_runs([STILL_QUEUED])[0] is True
    assert summarize_capture_runs([RUNNING])[0] is True


def test_finished_runs_are_not_in_flight() -> None:
    assert summarize_capture_runs([SUCCEEDED, FAILED, QUEUED_THEN_CANCELLED])[0] is False


def test_no_runs_today_is_a_clean_slate() -> None:
    assert summarize_capture_runs([]) == (False, 0)


def test_mixed_history_counts_only_what_executed() -> None:
    in_flight, reached = summarize_capture_runs(
        [QUEUED_THEN_CANCELLED, SUCCEEDED, QUEUED_THEN_CANCELLED, FAILED]
    )
    assert (in_flight, reached) == (False, 2)  # 2 of 4 actually ran
