"""The drift retrain fires once per drift episode per champion.

Drift is measured against the champion's training data, which a rejected candidate does not
change, so without a bound one persisting drift refits the market every session on a panel all but
identical to the one just rejected. London did exactly that on 2026-10-20, 21 and 22: a 0.308
share each day, three candidates, three rejections.
"""

import datetime as dt

from quantpulse.orchestration.catchup import drift_day_of, drift_retrain_due

D = dt.date(2026, 10, 19)


def days(*drifted: bool) -> list[tuple[dt.date, bool]]:
    """Drift checks newest first: days(True, True, False) is today and yesterday drifting."""
    return [(D - dt.timedelta(days=i), flag) for i, flag in enumerate(drifted)]


def test_a_new_drift_episode_fires() -> None:
    due, reason = drift_retrain_due(
        days(True, False, False), last_retrain_day=None, promoted_since=False
    )
    assert due and str(D) in reason


def test_londons_second_and_third_days_would_not_have_refitted() -> None:
    """Retrained for the episode's first day; the drift persists and the champion is unchanged."""
    due, reason = drift_retrain_due(
        days(True, True, True, False),
        last_retrain_day=D - dt.timedelta(days=2),
        promoted_since=False,
    )
    assert not due
    assert "already retrained" in reason and "champion has not changed" in reason


def test_a_new_champion_reopens_the_trigger() -> None:
    """Its drift is measured against new training data, so it is new evidence."""
    due, _ = drift_retrain_due(
        days(True, True, True), last_retrain_day=D - dt.timedelta(days=2), promoted_since=True
    )
    assert due


def test_drift_that_cleared_and_returned_is_a_new_episode() -> None:
    """Retrained in an earlier episode; the market calmed, then drifted again."""
    due, reason = drift_retrain_due(
        days(True, False, True, True),
        last_retrain_day=D - dt.timedelta(days=3),
        promoted_since=False,
    )
    assert due and str(D) in reason


def test_no_drift_never_fires_whatever_the_history() -> None:
    assert drift_retrain_due(days(False, True), None, True) == (False, "no drift beyond threshold")
    assert drift_retrain_due([], None, False)[0] is False


def test_the_drift_day_is_read_back_from_the_run_key() -> None:
    assert drift_day_of("drift-retrain-XLON-2026-10-19", "XLON") == D
    assert drift_day_of("drift-retrain-XJSE-2026-10-19", "XLON") is None
    assert drift_day_of("drift-retrain-XLON-not-a-date", "XLON") is None
    assert drift_day_of(None, "XLON") is None
