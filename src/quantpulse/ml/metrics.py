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
