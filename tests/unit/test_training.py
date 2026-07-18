"""Training tests on a small synthetic panel with a real (learnable) signal."""

import numpy as np
import pandas as pd
import pytest

from quantpulse.ml.training import (
    DEFAULT_PARAMS,
    TrainConfig,
    cross_validated_ic,
    train_final_model,
    tune_hyperparameters,
)

FEATURES = ["f1", "f2", "f3"]

CFG = TrainConfig(
    n_splits=3,
    embargo_days=5,
    min_train_dates=60,
    num_boost_round=60,
    early_stopping_rounds=10,
    optuna_trials=3,
)


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2023-01-02", periods=180).date
    rows = []
    for date in dates:
        for i in range(25):
            f1, f2, f3 = rng.normal(size=3)
            # fwd_ret depends on f1 and f2 with noise -> learnable signal
            fwd = 0.02 * f1 - 0.01 * f2 + rng.normal(0, 0.01)
            rows.append(
                {"ticker": f"T{i}", "date": date, "f1": f1, "f2": f2, "f3": f3, "fwd_ret": fwd}
            )
    return pd.DataFrame(rows)


def test_cross_validated_ic_learns_signal(frame: pd.DataFrame) -> None:
    ic = cross_validated_ic(frame, FEATURES, DEFAULT_PARAMS, CFG)
    assert ic > 0.3  # strong synthetic signal must be learnable


def test_cross_validated_ic_pure_noise_is_weak(frame: pd.DataFrame) -> None:
    noise = frame.copy()
    rng = np.random.default_rng(4)
    noise["fwd_ret"] = rng.normal(0, 0.01, len(noise))
    ic = cross_validated_ic(noise, FEATURES, DEFAULT_PARAMS, CFG)
    assert abs(ic) < 0.2


def test_tune_hyperparameters_respects_budget_and_improves(frame: pd.DataFrame) -> None:
    params = tune_hyperparameters(frame, FEATURES, CFG)
    assert set(DEFAULT_PARAMS) <= set(params)
    assert 1e-3 <= params["learning_rate"] <= 0.2


def test_train_final_model_holdout_is_out_of_sample(frame: pd.DataFrame) -> None:
    _booster, holdout = train_final_model(frame, FEATURES, DEFAULT_PARAMS, CFG)
    assert np.isfinite(holdout["pred"]).all()
    holdout_dates = set(holdout["date"])
    # Training may not have seen any holdout or embargo-adjacent dates.
    all_dates = sorted(frame["date"].unique())
    cut = min(holdout_dates)
    embargo_dates = set(all_dates[all_dates.index(cut) - CFG.embargo_days : all_dates.index(cut)])
    model_train_dates = set(all_dates) - holdout_dates - embargo_dates
    assert max(model_train_dates) < min(holdout_dates)
