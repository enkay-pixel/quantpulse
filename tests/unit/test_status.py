"""The dates `quantpulse status` puts ahead, checked against the exchange calendar by hand."""

import datetime as dt

from quantpulse.monitoring.status import (
    MarketStatus,
    live_sessions_reached,
    market_lines,
    next_retrain,
    sessions_ahead,
    shadow_summary,
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


def _market(exchange: str) -> MarketStatus:
    day = dt.date(2026, 10, 16)
    return MarketStatus(
        exchange=exchange,
        expected=day,
        prices=day,
        features=day,
        predictions=day,
        predictions_version="1",
        recent=(),
        champion="1",
        champion_since=day,
        rejections=0,
        shadow_recorded=0,
        shadow_due=2,
        shadow_in_window=8,
    )


def test_a_market_added_after_the_shadow_run_was_registered_is_not_counted_against_it() -> None:
    """London joined with two of the run's weeks already past. Counting them reads as two lost
    weeks of evidence, in a run whose verdict London was never part of."""
    assert shadow_summary(_market("XLON")).startswith("not in the shadow run")
    assert shadow_summary(_market("XNYS")) == "shadow weeks recorded 0 of 2 due (8 in window)"


def test_a_session_scored_without_listings_that_had_a_bar_is_reported() -> None:
    """The report counted prices per session, so New York's 2026-10-23, scored on 33 of its 50
    listings, read as a whole session."""
    from dataclasses import replace

    lines = market_lines(replace(_market("XNYS"), unscored=("AAPL", "MSFT")))
    (line,) = [ln for ln in lines if "scored without" in ln]
    assert line.startswith("  2026-10-16 scored without 2 listing(s) that had a bar: AAPL, MSFT")
    assert not any("scored without" in ln for ln in market_lines(_market("XNYS")))


def test_a_gap_a_retrain_has_used_is_reported_as_unfillable() -> None:
    from dataclasses import replace

    from quantpulse.monitoring.status import Session

    day = dt.date(2026, 10, 16)
    gap = Session(day, 49, 50, ("KO",))
    used = market_lines(replace(_market("XNYS"), recent=(gap,), trained_through=day))
    open_ = market_lines(
        replace(_market("XNYS"), recent=(gap,), trained_through=day - dt.timedelta(days=1))
    )
    assert any("nothing will fill it" in ln for ln in used)
    assert any("the sensor fills it" in ln for ln in open_)
