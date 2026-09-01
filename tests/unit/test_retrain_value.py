"""Whether retraining buys skill, measured on a shared forward window.

Two properties carry the result and are pinned here. Fresh and stale are compared at the same
seed, so seed-to-seed spread — which on this panel is larger than the effect being looked for
— differences out instead of being mistaken for a cadence effect. And seeds are averaged
inside a window before anything is pooled, so the sample counts windows rather than fits; the
alternative multiplies the apparent sample by the seed count and shrinks the error bar by its
square root, which is how a flat result is made to look sharp.
"""

import datetime as dt
from types import SimpleNamespace

import pandas as pd
import pytest

from quantpulse.ml import retrain_value as rv
from quantpulse.ml.training import TrainConfig

N_DATES = 900
STEP = 21


def _origins(n_dates: int = N_DATES, step: int = STEP) -> list[int]:
    cfg = TrainConfig()
    earliest = max(cfg.min_train_dates + cfg.embargo_days, n_dates // 2)
    return list(range(earliest, n_dates - step, step))


@pytest.fixture
def run_table(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Drive the comparison from an IC that is a known function of age, fitting nothing."""

    def _run(ic_for_age, seeds=(1, 2, 3), seed_offset=0.05):  # type: ignore[no-untyped-def]
        cfg = TrainConfig()
        dates = [dt.date(2020, 1, 1) + dt.timedelta(days=i) for i in range(N_DATES)]
        frame = pd.DataFrame({"date": dates, "x": range(N_DATES)})
        origins = _origins()
        window_index = {dates[o]: j for j, o in enumerate(origins)}
        state: dict = {}

        monkeypatch.setattr("quantpulse.ml.pipeline.build_dataset", lambda *a, **k: frame)
        monkeypatch.setattr(rv, "feature_columns_for", lambda ex: ["x"])
        monkeypatch.setattr(
            "quantpulse.ml.staleness._fit_frozen",
            lambda train, cols, c: SimpleNamespace(n_train=len(train), seed=c.seed),
        )

        def fake_predict(booster, scored):  # type: ignore[no-untyped-def]
            state["booster"] = booster
            state["window"] = window_index[min(scored["date"])]
            return [0.0] * len(scored)

        def fake_ic(scored):  # type: ignore[no-untyped-def]
            booster = state["booster"]
            fit_idx = (booster.n_train + cfg.embargo_days - origins[0]) // STEP
            age = state["window"] - fit_idx
            # A per-seed shift that must cancel: fresh and stale are compared at one seed.
            return ic_for_age(age) + booster.seed * seed_offset

        monkeypatch.setattr("quantpulse.ml.registry.predict_with", fake_predict)
        monkeypatch.setattr("quantpulse.ml.metrics.information_coefficient", fake_ic)
        return rv.retrain_value(object(), "XNYS", seeds=seeds, step_days=STEP, max_lag=3)

    return _run


def test_recovers_a_known_decay_and_cancels_the_seed_shift(run_table) -> None:  # type: ignore[no-untyped-def]
    """A model losing 0.01 IC per step should show exactly that much value in retraining."""
    table = run_table(lambda age: 0.10 - 0.01 * age)
    by_lag = {int(r["lag_days"]): r for r in table.to_dict("records")}

    assert set(by_lag) == {21, 42, 63}
    for steps, lag in ((1, 21), (2, 42), (3, 63)):
        assert by_lag[lag]["mean_delta"] == pytest.approx(0.01 * steps, abs=1e-9)
        # No spread across windows, so nothing is left for the error bar to report.
        assert by_lag[lag]["std_error"] == pytest.approx(0.0, abs=1e-9)
        assert by_lag[lag]["n_favour_fresh"] == by_lag[lag]["n_windows"]


def test_a_model_that_does_not_decay_shows_no_value_in_retraining(run_table) -> None:  # type: ignore[no-untyped-def]
    """Flat skill against age must not turn into a cadence effect."""
    table = run_table(lambda age: 0.10)
    for row in table.to_dict("records"):
        assert row["mean_delta"] == pytest.approx(0.0, abs=1e-9)


def test_sample_counts_windows_not_fits(run_table) -> None:  # type: ignore[no-untyped-def]
    """Adding seeds must sharpen each window's estimate, never enlarge the sample."""
    few = run_table(lambda age: 0.10 - 0.01 * age, seeds=(1, 2))
    many = run_table(lambda age: 0.10 - 0.01 * age, seeds=(1, 2, 3, 4, 5))

    n_few = {int(r["lag_days"]): r["n_windows"] for r in few.to_dict("records")}
    n_many = {int(r["lag_days"]): r["n_windows"] for r in many.to_dict("records")}
    assert n_few == n_many
    # Windows available at a lag are the origins that have a partner that far back.
    assert n_few[21] == len(_origins()) - 1
    assert n_few[63] == len(_origins()) - 3


def test_error_bar_widens_when_neighbouring_windows_move_together() -> None:
    """Windows are not independent, so the error bar must not be the independent one."""
    drifting = [(-1.0) ** 0 * 0.01 * i for i in range(40)]  # a slow trend: strongly correlated
    alternating = [0.01 * (-1.0) ** i for i in range(40)]  # flips every window: anti-correlated

    independent = rv._newey_west([0.0] * 40, max_lag=3)
    assert independent == pytest.approx(0.0)
    assert rv._newey_west(drifting, max_lag=3) > 0
    # Anti-correlated neighbours cancel, so the allowance is smaller than the trending case.
    assert rv._newey_west(alternating, max_lag=3) < rv._newey_west(drifting, max_lag=3)
