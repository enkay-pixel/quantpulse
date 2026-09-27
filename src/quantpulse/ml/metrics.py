"""Performance metrics (replaces the unmaintained `empyrical` dependency)."""

import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS_PER_YEAR = 252
MONTHS_PER_YEAR = 12


def annualized_return(returns: pd.Series, periods_per_year: int) -> float:
    """Geometric annualized return from per-period simple returns."""
    if returns.empty:
        return float("nan")
    growth = float(np.prod(1 + returns.to_numpy()))
    if growth <= 0:
        return -1.0
    return growth ** (periods_per_year / len(returns)) - 1


def annualized_volatility(returns: pd.Series, periods_per_year: int) -> float:
    if len(returns) < 2:
        return float("nan")
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(returns: pd.Series, periods_per_year: int, risk_free: float = 0.0) -> float:
    """Annualized Sharpe from per-period simple returns (rf given as annual rate)."""
    if len(returns) < 2:
        return float("nan")
    excess = returns - risk_free / periods_per_year
    vol = excess.std(ddof=1)
    if np.isclose(vol, 0):  # constant returns have no defined risk-adjusted ratio
        return float("nan")
    return float(excess.mean() / vol * np.sqrt(periods_per_year))


def max_drawdown(returns: pd.Series) -> float:
    """Most negative peak-to-trough drawdown of the compounded equity curve (<= 0)."""
    if returns.empty:
        return float("nan")
    equity = (1 + returns).cumprod()
    peak = equity.cummax()
    return float((equity / peak - 1).min())


def information_coefficient(frame: pd.DataFrame) -> float:
    """Mean per-date Spearman rank correlation between `pred` and `fwd_ret` columns."""
    ics = []
    for _, group in frame.groupby("date"):
        if len(group) < 3 or group["pred"].nunique() < 2 or group["fwd_ret"].nunique() < 2:
            continue
        ic = stats.spearmanr(group["pred"], group["fwd_ret"]).statistic
        if not np.isnan(ic):
            ics.append(ic)
    return float(np.mean(ics)) if ics else float("nan")


def summarize_returns(returns: pd.Series, periods_per_year: int) -> dict[str, float]:
    return {
        "annual_return": annualized_return(returns, periods_per_year),
        "annual_volatility": annualized_volatility(returns, periods_per_year),
        "sharpe": sharpe_ratio(returns, periods_per_year),
        "max_drawdown": max_drawdown(returns),
        "n_periods": float(len(returns)),
    }


def newey_west_se(values: list[float], max_lag: int) -> float:
    """Standard error of the mean that allows neighbouring observations to be correlated.

    Weights fall linearly with distance so the estimate stays non-negative.

    Lives here rather than beside any one study because every rolling-origin measurement in
    this package needs it: overlapping holdouts and forward labels that straddle window
    boundaries make neighbouring origins correlated, and the plain standard error then reports
    a sample larger than the period actually contains.
    """
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    resid = arr - arr.mean()
    var = float(resid @ resid) / n
    for lag in range(1, min(max_lag, n - 1) + 1):
        cov = float(resid[lag:] @ resid[:-lag]) / n
        var += 2.0 * (1.0 - lag / (max_lag + 1)) * cov
    return float(np.sqrt(max(var, 0.0) / n))


def lag1_autocorrelation(values: list[float]) -> float:
    """Lag-1 autocorrelation of a series, as a check on whether its samples are independent.

    Rolling-origin studies here produce series whose neighbours share almost all of their
    history, so the standard error has to allow for correlation. This reports how much there is
    instead of assuming a lag width is enough: a value near zero says the plain error would have
    been fine, and a large one says the effective sample is well below the number of rows.
    """
    arr = np.asarray(values, dtype=float)
    if len(arr) < 3:
        return float("nan")
    resid = arr - arr.mean()
    denom = float(resid @ resid)
    if denom == 0.0:
        return float("nan")
    return float(resid[1:] @ resid[:-1]) / denom
