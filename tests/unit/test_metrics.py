import numpy as np
import pandas as pd

from quantpulse.ml.metrics import (
    annualized_return,
    annualized_volatility,
    information_coefficient,
    max_drawdown,
    sharpe_ratio,
    summarize_returns,
)


def test_annualized_return_constant_monthly() -> None:
    returns = pd.Series([0.01] * 12)
    assert annualized_return(returns, 12) == (1.01**12 - 1)


def test_annualized_volatility_scaling() -> None:
    returns = pd.Series([0.02, -0.02] * 6)
    assert np.isclose(annualized_volatility(returns, 12), returns.std(ddof=1) * np.sqrt(12))


def test_sharpe_of_constant_returns_is_nan() -> None:
    assert np.isnan(sharpe_ratio(pd.Series([0.01] * 10), 12))


def test_sharpe_sign_matches_mean() -> None:
    up = pd.Series([0.02, 0.01, 0.03, 0.015])
    down = -up
    assert sharpe_ratio(up, 252) > 0 > sharpe_ratio(down, 252)


def test_max_drawdown_known_path() -> None:
    # equity: 1.1, 0.88 (peak 1.1 -> -20%), 0.968
    returns = pd.Series([0.10, -0.20, 0.10])
    assert np.isclose(max_drawdown(returns), -0.20)


def test_information_coefficient_perfect_and_inverted() -> None:
    rows = []
    for day in ["2024-01-02", "2024-01-03"]:
        for i in range(10):
            rows.append({"date": day, "pred": i, "fwd_ret": i * 0.01})
    frame = pd.DataFrame(rows)
    assert np.isclose(information_coefficient(frame), 1.0)
    frame["pred"] = -frame["pred"]
    assert np.isclose(information_coefficient(frame), -1.0)


def test_summarize_returns_keys() -> None:
    stats = summarize_returns(pd.Series([0.01, -0.005, 0.02]), 12)
    assert set(stats) == {
        "annual_return",
        "annual_volatility",
        "sharpe",
        "max_drawdown",
        "n_periods",
    }
