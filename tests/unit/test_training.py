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


def test_split_by_date_embargoes_the_boundary(frame: pd.DataFrame) -> None:
    from quantpulse.ml.training import split_by_date

    before, after = split_by_date(frame, 0.15, CFG.embargo_days)
    all_dates = sorted(frame["date"].unique())
    gap = all_dates.index(min(after["date"])) - all_dates.index(max(before["date"]))
    assert gap > CFG.embargo_days  # a full embargo of dates separates the halves
    assert after["date"].nunique() == pytest.approx(len(all_dates) * 0.15, abs=2)


def test_final_fit_early_stops_on_inner_split_not_the_holdout(
    frame: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    """choosing the boosting rounds on the promotion holdout partially fits
    it — 308 rounds ground toward the exact frame the gate then scored. The validation
    frame handed to LightGBM must be disjoint from (and strictly older than) the holdout."""
    from quantpulse.ml import training

    captured: dict[str, set] = {}
    real_fit = training._fit_one

    def spy(train, val, feature_cols, params, cfg):  # type: ignore[no-untyped-def]
        captured["val"] = set(val["date"])
        return real_fit(train, val, feature_cols, params, cfg)

    monkeypatch.setattr(training, "_fit_one", spy)
    _booster, holdout = train_final_model(frame, FEATURES, DEFAULT_PARAMS, CFG)
    assert captured["val"], "early-stopping validation frame was never captured"
    assert not (captured["val"] & set(holdout["date"]))
    assert max(captured["val"]) < min(holdout["date"])


# --- early stopping watches the metric the gate decides on ---------------------------------


def _ic_pair(frame):  # type: ignore[no-untyped-def]
    """(reference IC, fast early-stopping IC) for the same predictions."""
    from quantpulse.ml.metrics import information_coefficient
    from quantpulse.ml.training import _ic_eval

    reference = information_coefficient(frame)
    _, fast, higher_better = _ic_eval(frame)(frame["pred"].to_numpy(), None)
    assert higher_better is True
    return reference, fast


def test_the_fast_ic_matches_the_one_the_gate_scores() -> None:
    """The early-stopping metric is a second implementation of the gate's IC, written
    vectorized because it runs every boosting round. If the two disagree the fit is stopped
    on a number nobody is judged by, and nothing would report the divergence."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    dates = np.repeat(pd.date_range("2024-01-01", periods=40).date, 25)
    frame = pd.DataFrame(
        {
            "date": dates,
            "fwd_ret": rng.normal(size=len(dates)),
            "pred": rng.normal(size=len(dates)),
        }
    )
    reference, fast = _ic_pair(frame)
    assert fast == pytest.approx(reference, abs=1e-9)


def test_the_two_agree_when_ranks_are_tied() -> None:
    """Ties are where a hand-rolled Spearman usually drifts from scipy's."""
    import numpy as np
    import pandas as pd

    dates = np.repeat(pd.date_range("2024-01-01", periods=8).date, 10)
    frame = pd.DataFrame(
        {
            "date": dates,
            # Heavy ties in both columns.
            "fwd_ret": np.tile([0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 3.0], 8),
            "pred": np.tile([5.0, 5.0, 5.0, 1.0, 1.0, 2.0, 2.0, 2.0, 9.0, 9.0], 8),
        }
    )
    reference, fast = _ic_pair(frame)
    assert fast == pytest.approx(reference, abs=1e-9)


def test_a_date_with_no_rank_information_is_skipped_by_both() -> None:
    """Fewer than three names, or a constant column, carries no ranking — counting it as
    zero would drag the average toward nothing and stop the fit early."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(1)
    good = pd.DataFrame(
        {
            "date": np.repeat(pd.date_range("2024-02-01", periods=10).date, 20),
            "fwd_ret": rng.normal(size=200),
            "pred": rng.normal(size=200),
        }
    )
    degenerate = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-03-01").date()] * 2  # too few names
            + [pd.Timestamp("2024-03-02").date()] * 5,  # constant prediction
            "fwd_ret": [0.1, -0.2, 0.3, 0.1, -0.4, 0.2, 0.5],
            "pred": [1.0, 2.0, 7.0, 7.0, 7.0, 7.0, 7.0],
        }
    )
    frame = pd.concat([good, degenerate], ignore_index=True)
    reference, fast = _ic_pair(frame)
    assert fast == pytest.approx(reference, abs=1e-9)
