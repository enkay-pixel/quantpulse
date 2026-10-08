"""Guards on the forward scorer, on synthetic data whose answers are known.

The scorer applies a rule fixed before the shadow ran, so what has to be pinned is that it applies
that rule and no other: the window it reads, the weeks it counts as lost, the side of the bound it
compares, and the day it calls a retrain's. Each is tested against a case worked by hand rather than
against real forward returns, which would be a look at the result before the window closes.
"""

import datetime as dt
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from quantpulse.ml import shadow_forward as sf
from quantpulse.ml.shadow_forward import (
    FORWARD_SESSIONS,
    NEWEY_WEST_LAG,
    Week,
    due,
    forward_ic,
    forward_window,
    reproduces,
    saturdays,
    verdict,
    week_scores,
    weekly_pairs,
)

MARGIN = 0.008


def test_the_window_is_the_eight_pre_registered_saturdays() -> None:
    days = saturdays()
    assert days[0] == dt.date(2026, 10, 10) and days[-1] == dt.date(2026, 11, 28)
    assert len(days) == 8
    assert all(d.weekday() == 5 for d in days)
    with pytest.raises(ValueError):
        saturdays(dt.date(2026, 10, 9), dt.date(2026, 11, 28))


def test_a_retrain_is_not_due_until_its_saturday_has_passed() -> None:
    """A run on the Saturday morning, before the retrain fires, must not count it as missing."""
    first, second = saturdays()[:2]
    assert due([first, second], today=first) == []
    assert due([first, second], today=first + dt.timedelta(days=1)) == [first]
    assert due([first, second], today=second + dt.timedelta(days=1)) == [first, second]


def _panel(dates: list[dt.date], tickers: int = 5) -> pd.DataFrame:
    rows = []
    for d in dates:
        for t in range(tickers):
            rows.append({"date": d, "ticker": f"T{t}", "f": float(t), "fwd_ret": float(t)})
    return pd.DataFrame(rows)


def test_forward_window_starts_after_the_holdout_and_stops_at_the_label_horizon() -> None:
    days = [dt.date(2026, 9, 1) + dt.timedelta(days=i) for i in range(40)]
    holdout_end = days[9]
    forward, n = forward_window(_panel(days), holdout_end)
    assert n == FORWARD_SESSIONS == 21
    assert min(forward["date"]) == days[10], "the holdout's own last day leaked into the window"
    assert max(forward["date"]) == days[30]


def test_a_window_with_too_few_matured_sessions_says_how_many() -> None:
    days = [dt.date(2026, 9, 1) + dt.timedelta(days=i) for i in range(15)]
    _, n = forward_window(_panel(days), days[9])
    assert n == 5


class _Booster:
    """Predicts a fixed column, so the IC it earns is known in advance."""

    def __init__(self, sign: float) -> None:
        self.sign = sign

    def feature_name(self) -> list[str]:
        return ["f"]

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return self.sign * x["f"].to_numpy()


def test_forward_ic_is_the_gates_per_session_rank_ic() -> None:
    days = [dt.date(2026, 9, 1) + dt.timedelta(days=i) for i in range(3)]
    panel = _panel(days)  # prediction and return both rise with the ticker index
    assert forward_ic(_Booster(+1.0), panel) == pytest.approx(1.0)
    assert forward_ic(_Booster(-1.0), panel) == pytest.approx(-1.0)


def test_a_refit_counts_as_its_week_only_if_it_reproduces_the_recorded_score() -> None:
    assert reproduces(0.0352071, 0.0352071)
    assert not reproduces(0.0352071, 0.0352072), "a different model was accepted as this week's"
    assert not reproduces(0.035, None)


def _week(day: int, status: str = "scored", delta: float | None = 0.0) -> Week:
    return Week(dt.date(2026, 10, 10) + dt.timedelta(weeks=day), "XJSE", "14", "2026-09-02",
                status, 21 if status == "scored" else 0, 0.03, 0.03, delta, "")  # fmt: skip


def test_nothing_is_read_until_every_retrain_in_the_window_has_happened() -> None:
    v = verdict([_week(i) for i in range(5)], MARGIN, expected=8)
    assert v["state"] == "not_yet_readable"


def test_nothing_is_read_while_any_window_is_still_maturing() -> None:
    weeks = [_week(i) for i in range(7)] + [_week(7, status="maturing", delta=None)]
    assert verdict(weeks, MARGIN, expected=8)["state"] == "not_yet_readable"


def test_two_lost_weeks_make_the_run_not_clean() -> None:
    weeks = [_week(i) for i in range(6)] + [
        _week(6, status="shadow_missing", delta=None),
        _week(7, status="unrecoverable", delta=None),
    ]
    v = verdict(weeks, MARGIN, expected=8)
    assert v["state"] == "not_clean" and v["lost"] == 2


def test_one_lost_week_is_tolerated_and_the_rest_are_read() -> None:
    weeks = [_week(i, delta=0.001) for i in range(7)] + [_week(7, status="unpaired", delta=None)]
    v = verdict(weeks, MARGIN, expected=8)
    assert v["state"] in {"harm_shown", "no_harm_shown"}
    assert v["weeks"] == 7 and v["lost"] == 1


def test_clear_harm_keeps_the_tuner() -> None:
    deltas = [-0.030, -0.028, -0.031, -0.029, -0.027, -0.030, -0.032, -0.029]
    v = verdict([_week(i, delta=d) for i, d in enumerate(deltas)], MARGIN, expected=8)
    assert v["state"] == "harm_shown"
    assert v["action"] == "keep the tuner"
    assert v["upper_bound"] < -MARGIN


def test_noise_around_zero_does_not_stop_the_switch() -> None:
    """The burden sits on harm: an unfavourable but unresolved result must not read as harm.

    The mean here is deliberately negative. A noise test whose mean happened to be positive would
    pass under a rule that stopped the switch on any negative mean, and so would not test the
    direction of the burden at all.
    """
    deltas = [0.02, -0.03, 0.01, -0.02, 0.01, -0.03, 0.0, 0.005]
    assert sum(deltas) / len(deltas) < 0, "the case must be unfavourable to test anything"
    v = verdict([_week(i, delta=d) for i, d in enumerate(deltas)], MARGIN, expected=8)
    assert v["state"] == "no_harm_shown"


def test_the_harm_test_uses_the_upper_bound_and_a_strict_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Harm needs the defaults worse even at their most favourable — the upper bound, not the mean
    — and a bound exactly on the margin is not past it."""
    deltas = [-0.010] * 8
    monkeypatch.setattr(sf, "newey_west_se", lambda d, max_lag: 0.0)
    # Mean -0.010 is past the margin and so is the bound, with no error to widen it.
    assert verdict([_week(i, delta=d) for i, d in enumerate(deltas)], MARGIN, 8)["state"] == (
        "harm_shown"
    )
    # Same mean, but an error wide enough that the upper bound is back inside: not harm.
    monkeypatch.setattr(sf, "newey_west_se", lambda d, max_lag: 0.005)
    assert verdict([_week(i, delta=d) for i, d in enumerate(deltas)], MARGIN, 8)["state"] == (
        "no_harm_shown"
    )
    # Exactly on the margin: strict, so not harm.
    monkeypatch.setattr(sf, "newey_west_se", lambda d, max_lag: 0.0)
    on_line = [-MARGIN] * 8
    assert verdict([_week(i, delta=d) for i, d in enumerate(on_line)], MARGIN, 8)["state"] == (
        "no_harm_shown"
    )


def test_the_error_allows_for_the_overlap_between_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def spy(deltas: list[float], max_lag: int) -> float:
        seen["lag"] = max_lag
        return 0.001

    monkeypatch.setattr(sf, "newey_west_se", spy)
    verdict([_week(i, delta=0.0) for i in range(8)], MARGIN, expected=8)
    assert seen["lag"] == NEWEY_WEST_LAG == 4


class _Scalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Session:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self, _q: object) -> _Scalars:
        return _Scalars(self._rows)


def _row(id_: int, run_type: str, utc: str, **metrics: Any) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_,
        run_type=run_type,
        created_at=dt.datetime.fromisoformat(utc).replace(tzinfo=dt.UTC),
        metrics=metrics,
        model_version=str(id_),
    )


def test_a_retrain_is_dated_in_new_york_not_in_utc() -> None:
    """03:00 UTC on a Saturday is still Friday in New York. A drift retrain at that hour is not the
    Saturday scheduled one, and reading the date in UTC would file it as if it were."""
    saturday = dt.date(2026, 10, 10)
    friday_night_drift = _row(1, "train", "2026-10-10T03:00:00")  # Fri 23:00 New York
    scheduled = _row(2, "train", "2026-10-10T13:00:00")  # Sat 09:00 New York
    shadow = _row(3, "shadow", "2026-10-10T13:05:00", shadows_run_id=2, paired=True)
    pairs = weekly_pairs(_Session([friday_night_drift, scheduled, shadow]), "XJSE", [saturday])
    production, paired_shadow = pairs[saturday]
    assert production is scheduled, "a Friday-night drift retrain was taken for Saturday's"
    assert paired_shadow is shadow


def test_a_shadow_pairs_with_its_own_candidate_and_no_other() -> None:
    saturday = dt.date(2026, 10, 17)
    scheduled = _row(10, "train", "2026-10-17T13:00:00")
    stray = _row(11, "shadow", "2026-10-17T13:05:00", shadows_run_id=9, paired=True)
    pairs = weekly_pairs(_Session([scheduled, stray]), "XJSE", [saturday])
    assert pairs[saturday] == (scheduled, None)


def test_missing_and_unpaired_weeks_are_lost_without_fitting_anything() -> None:
    cfg: Any = SimpleNamespace()
    day = dt.date(2026, 10, 10)
    assert sf.score_week(pd.DataFrame(), "XJSE", day, None, None, cfg).status == "no_retrain"
    prod = _row(2, "train", "2026-10-10T13:00:00", holdout_end="2026-09-02", holdout_ic=0.03)
    assert sf.score_week(pd.DataFrame(), "XJSE", day, prod, None, cfg).status == "shadow_missing"
    unpaired = _row(3, "shadow", "2026-10-10T13:05:00", shadows_run_id=2, paired=False)
    assert sf.score_week(pd.DataFrame(), "XJSE", day, prod, unpaired, cfg).status == "unpaired"


@pytest.mark.parametrize("state", ["not_yet_readable", "not_clean"])
def test_scores_are_withheld_until_the_rule_can_be_read(state: str) -> None:
    """Shown early, each week's difference is a look at noise, and under a rule that stops the
    switch only on harm, enough looks stop it. Health and progress are shown; scores are not."""
    for status in ("scored", "maturing"):
        text = week_scores(_week(0, status=status, delta=-0.05), state)
        assert "-0.05" not in text and "diff" not in text, f"scores leaked while {state}"
        assert "withheld" in text


@pytest.mark.parametrize("state", ["harm_shown", "no_harm_shown"])
def test_scores_are_shown_once_the_rule_has_been_read(state: str) -> None:
    assert "diff -0.0500" in week_scores(_week(0, delta=-0.05), state)
