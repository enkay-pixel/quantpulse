"""Guards on the champion's forward comparison, on synthetic data whose answers are known.

What has to be pinned is that the comparison reads the window and the rule the pre-registration
fixed: where the model's holdout ends and its forward window begins, that per-session ICs are the
gate's own, that the two signals are always compared over the same sessions, and which side of the
bound each verdict needs.
"""

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd
import pytest

from quantpulse.ml import champion_forward as cf
from quantpulse.ml.champion_forward import compare, daily_ic, forward_bounds
from quantpulse.ml.metrics import information_coefficient

HORIZON = 21
SESSIONS = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(80)]


def test_the_forward_window_starts_the_session_after_the_last_label_the_model_saw() -> None:
    """Data ending at session 40 holds labels only up to session 19: those are the model's. The
    window starts at 20 and runs to the last label matured by as_of."""
    holdout_end, first, last = forward_bounds(SESSIONS, SESSIONS[40], SESSIONS[70], HORIZON)
    assert holdout_end == SESSIONS[19]
    assert first == SESSIONS[20], "the window overlaps the labels the model was chosen on"
    assert last == SESSIONS[49], "the window includes a label not yet matured at as_of"


def test_the_window_matches_the_pre_registered_dates_on_a_real_calendar() -> None:
    """The pre-registration's dates were laid from the XJSE calendar; the same rule on a weekday
    calendar must land on a holdout end 21 sessions before the data end."""
    weekdays = list(pd.bdate_range("2026-05-01", "2026-10-30").date)
    holdout_end, first, _ = forward_bounds(
        weekdays, dt.date(2026, 7, 24), dt.date(2026, 10, 9), HORIZON
    )
    assert weekdays.index(dt.date(2026, 7, 24)) - weekdays.index(holdout_end) == HORIZON
    assert weekdays.index(first) == weekdays.index(holdout_end) + 1


def test_dates_that_are_not_sessions_are_refused() -> None:
    with pytest.raises(ValueError, match="not a trading session"):
        forward_bounds(SESSIONS, dt.date(2025, 1, 1), SESSIONS[70], HORIZON)
    with pytest.raises(ValueError, match="no forward session"):
        forward_bounds(SESSIONS, SESSIONS[40], SESSIONS[40], HORIZON)


def _panel(rng: np.random.Generator, days: int = 6, tickers: int = 8) -> pd.DataFrame:
    rows = []
    for d in range(days):
        for t in range(tickers):
            rows.append(
                {
                    "date": dt.date(2026, 3, 1) + dt.timedelta(days=d),
                    "ticker": f"T{t}",
                    "a": rng.normal(),
                    "fwd_ret": rng.normal(),
                }
            )
    return pd.DataFrame(rows)


def test_per_session_ic_averages_to_the_gates_ic() -> None:
    """A second implementation of the scoring rule is a known way for two numbers to agree with each
    other and disagree with the gate, so the per-session values must average to its exact figure."""
    panel = _panel(np.random.default_rng(1))
    gate = information_coefficient(panel.assign(pred=panel["a"]))
    assert daily_ic(panel, "a").mean() == pytest.approx(gate, abs=1e-12)


def test_a_session_with_a_constant_score_has_no_ic() -> None:
    panel = _panel(np.random.default_rng(2))
    first = panel["date"].min()
    panel.loc[panel["date"] == first, "a"] = 0.5
    ics = daily_ic(panel, "a")
    assert np.isnan(ics[first]) and ics.drop(first).notna().all()


def test_a_session_with_too_few_tickers_has_no_ic() -> None:
    """Two tickers always rank-correlate at exactly plus or minus one, which is not evidence."""
    panel = _panel(np.random.default_rng(3))
    first = panel["date"].min()
    panel = panel[(panel["date"] != first) | panel["ticker"].isin(["T0", "T1"])]
    ics = daily_ic(panel, "a")
    assert np.isnan(ics[first]) and ics.drop(first).notna().all()


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=SESSIONS[: len(values)], dtype=float)


def test_both_signals_are_compared_over_the_same_sessions() -> None:
    """A session the model cannot be scored on must drop out of the competitor's mean too, or the
    difference compares two different sets of sessions."""
    model = _series([0.1, float("nan"), 0.1, 0.1])
    competitor = _series([0.0, 0.9, 0.0, 0.0])
    r = compare(model, competitor, HORIZON)
    assert r["sessions"] == 3
    assert r["competitor_ic"] == pytest.approx(0.0), "the dropped session leaked into one side"
    assert r["mean_delta"] == pytest.approx(0.1)


def test_each_verdict_needs_its_own_side_of_the_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cf, "newey_west_se", lambda d, max_lag: 0.01)
    ahead = compare(_series([0.05] * 30), _series([0.0] * 30), HORIZON)
    behind = compare(_series([0.0] * 30), _series([0.05] * 30), HORIZON)
    close = compare(_series([0.01] * 30), _series([0.0] * 30), HORIZON)
    assert ahead["state"] == "model_ahead" and ahead["lower_bound"] > 0
    assert behind["state"] == "competitor_ahead" and behind["upper_bound"] < 0
    assert close["state"] == "not_resolved"
    assert close["sessions_needed"] == pytest.approx(30 * (1.645 * 0.01 / 0.01) ** 2)
    assert ahead["sessions_needed"] is None, "a resolved result was given a sample to wait for"


def test_a_bound_exactly_on_zero_does_not_resolve() -> None:
    """Identical signals have both bounds exactly on zero; neither side may claim them."""
    same = compare(_series([0.03] * 30), _series([0.03] * 30), HORIZON)
    assert same["lower_bound"] == 0.0 and same["upper_bound"] == 0.0
    assert same["state"] == "not_resolved"
    assert same["sessions_needed"] is None, "a zero mean was given a finite sample to wait for"


def test_the_error_allows_for_overlapping_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def spy(diffs: list[float], max_lag: int) -> float:
        seen["lag"] = max_lag
        return 0.01

    monkeypatch.setattr(cf, "newey_west_se", spy)
    compare(_series([0.0] * 30), _series([0.0] * 30), HORIZON)
    assert seen["lag"] == 20, "each 21-session label overlaps the next twenty"


def test_blocks_are_consecutive_label_horizons() -> None:
    diffs = [1.0] * 21 + [2.0] * 21 + [3.0] * 11
    r = compare(_series(diffs), _series([0.0] * 53), HORIZON)
    assert r["block_deltas"] == pytest.approx([1.0, 2.0, 3.0])


def test_too_few_sessions_reads_nothing() -> None:
    r = compare(_series([0.1]), _series([0.0]), HORIZON)
    assert r["state"] == "too_few_sessions" and "mean_delta" not in r
