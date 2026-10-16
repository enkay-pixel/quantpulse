"""The dates `quantpulse status` puts ahead, checked against the exchange calendar by hand."""

import datetime as dt

from quantpulse.monitoring.status import (
    live_sessions_reached,
    next_retrain,
    sessions_ahead,
    shadow_verdict_eta,
)


def test_the_next_retrain_is_the_coming_saturday_or_today_on_one() -> None:
    assert next_retrain(dt.date(2026, 10, 14)) == dt.date(2026, 10, 17)  # a Wednesday
    assert next_retrain(dt.date(2026, 10, 17)) == dt.date(2026, 10, 17)  # a Saturday
    assert next_retrain(dt.date(2026, 10, 18)) == dt.date(2026, 10, 24)  # a Sunday


def test_sessions_ahead_skips_weekends_and_holidays() -> None:
    # Thanksgiving, Thursday 2026-11-26, is not a session; the Friday half day is.
    assert sessions_ahead(dt.date(2026, 11, 24), 2, "XNYS") == dt.date(2026, 11, 27)
    assert sessions_ahead(dt.date(2026, 10, 16), 1, "XNYS") == dt.date(2026, 10, 19)


def test_the_shadow_verdict_waits_for_the_last_windows_labels() -> None:
    """The last retrain (2026-11-28) fits on data to 2026-11-27; its forward window ends there,
    and those labels mature 21 sessions later — past Christmas, which is not a session."""
    assert shadow_verdict_eta() == dt.date(2026, 12, 29)


def test_a_live_session_count_is_dated_by_the_close_that_completes_it() -> None:
    """A record ending Wednesday 2026-10-14 at 58 sessions holds its 60th return on Friday's
    session, but that return needs Monday's close: the count of 60 is readable on 2026-10-19,
    not 2026-10-16."""
    assert live_sessions_reached(dt.date(2026, 10, 14), 58, 60, "XJSE") == dt.date(2026, 10, 19)
    # Already there: the next close still has to land before anything new is readable.
    assert live_sessions_reached(dt.date(2026, 10, 14), 60, 60, "XJSE") == dt.date(2026, 10, 15)
