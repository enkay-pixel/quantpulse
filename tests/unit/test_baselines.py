"""The simpler-model baselines, and the properties that make them a fair comparison.

These exist because the ML Test Score audit scored "a simpler model is not better" at zero:
the promotion gate only ever compared a challenger against the previous champion, so a whole
lineage could beat each other while losing to a one-line rule.

What matters here is not that each baseline is clever — two of them are deliberately trivial
— but that they are *comparable*: same rows, same feature columns, no peeking at the target
on the holdout, and deterministic so a rerun does not move the verdict.
"""

import numpy as np
import pandas as pd
import pytest

from quantpulse.features.engineering import FEATURE_COLUMNS, LABEL_COLUMN
from quantpulse.ml.baselines import BASELINES, _momentum, _noise, _reversal, _ridge

COLS = list(FEATURE_COLUMNS)


def _frame(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = {c: rng.normal(size=n) for c in COLS}
    data[LABEL_COLUMN] = rng.normal(size=n)
    data["ticker"] = [f"T{i % 5}" for i in range(n)]
    data["date"] = pd.to_datetime("2026-01-01") + pd.to_timedelta(np.arange(n) // 5, unit="D")
    return pd.DataFrame(data)


TRAIN = _frame(200, 1)
HOLDOUT = _frame(50, 2)


@pytest.mark.parametrize("name", sorted(BASELINES))
def test_every_baseline_returns_one_score_per_holdout_row(name: str) -> None:
    """A shape mismatch would silently misalign scores against tickers, which reads as a
    weak signal rather than as a bug."""
    preds = BASELINES[name](TRAIN, HOLDOUT, COLS)
    assert preds.shape == (len(HOLDOUT),)
    assert np.isfinite(preds).all(), f"{name} produced non-finite scores"


@pytest.mark.parametrize("name", sorted(BASELINES))
def test_every_baseline_is_deterministic(name: str) -> None:
    """A baseline that moves between runs cannot settle an argument about the champion."""
    first = BASELINES[name](TRAIN, HOLDOUT, COLS)
    second = BASELINES[name](TRAIN, HOLDOUT, COLS)
    np.testing.assert_array_equal(first, second)


def test_no_baseline_reads_the_holdout_target() -> None:
    """The comparison is worthless if a baseline can see the answer. Scores must be
    unchanged when the holdout's target column is destroyed."""
    blinded = HOLDOUT.copy()
    blinded[LABEL_COLUMN] = np.nan
    for name, fn in BASELINES.items():
        np.testing.assert_array_equal(
            fn(TRAIN, HOLDOUT, COLS), fn(TRAIN, blinded, COLS), err_msg=f"{name} peeked"
        )


def test_momentum_is_exactly_the_momentum_feature() -> None:
    """Zero parameters and zero fitting is the whole point — if this ever becomes a
    transformation of the column, it stops being the literature's rule."""
    np.testing.assert_array_equal(
        _momentum(TRAIN, HOLDOUT, COLS), HOLDOUT["mom_63_cs_rank"].to_numpy(float)
    )


def test_reversal_is_the_opposite_sign_of_recent_return() -> None:
    np.testing.assert_array_equal(
        _reversal(TRAIN, HOLDOUT, COLS), -HOLDOUT["ret_21_cs_rank"].to_numpy(float)
    )


def test_noise_ignores_the_features_entirely() -> None:
    """The floor has to be a floor: if it responded to the features it would stop measuring
    what this backtest returns from a signal containing nothing."""
    shuffled = HOLDOUT.copy()
    for c in COLS:
        shuffled[c] = shuffled[c].to_numpy()[::-1]
    np.testing.assert_array_equal(_noise(TRAIN, HOLDOUT, COLS), _noise(TRAIN, shuffled, COLS))


def test_ridge_recovers_a_linear_relationship() -> None:
    """Sanity on the hand-rolled solver: given a target that *is* a feature, the fit should
    track it closely. A broken normal-equations solve would otherwise look like 'the linear
    baseline is weak' rather than 'the linear baseline is wrong'."""
    train = TRAIN.copy()
    train[LABEL_COLUMN] = 3.0 * train[COLS[0]]
    holdout = HOLDOUT.copy()
    preds = _ridge(train, holdout, COLS)
    corr = np.corrcoef(preds, holdout[COLS[0]].to_numpy(float))[0, 1]
    assert corr > 0.95, f"ridge failed to recover a linear signal (corr={corr:.3f})"


def test_ridge_survives_a_constant_feature() -> None:
    """A zero-variance column makes the standardisation divide by zero; real panels get
    them whenever a market halts or a feature saturates."""
    train = TRAIN.copy()
    train[COLS[1]] = 1.0
    holdout = HOLDOUT.copy()
    holdout[COLS[1]] = 1.0
    assert np.isfinite(_ridge(train, holdout, COLS)).all()


def test_ridge_refuses_to_fit_on_nothing() -> None:
    """A target that fails to compute filters every row away. Fitting on the remainder
    returns coefficients from nothing and the baseline scores as "no signal" — the most
    misleading answer available, because it reads as evidence *for* the champion."""
    train = TRAIN.copy()
    train[LABEL_COLUMN] = np.inf
    with pytest.raises(ValueError, match="more usable rows than features"):
        _ridge(train, HOLDOUT, COLS)


def test_ridge_refuses_an_underdetermined_fit() -> None:
    """Fewer rows than features fits the training set exactly and predicts noise."""
    with pytest.raises(ValueError, match="more usable rows than features"):
        _ridge(TRAIN.head(len(COLS)), HOLDOUT, COLS)
