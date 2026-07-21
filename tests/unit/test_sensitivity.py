import numpy as np
import pandas as pd
import pytest

from quantpulse.ml.backtest import BacktestConfig, run_backtest
from quantpulse.ml.sensitivity import breakeven_cost, cost_sensitivity


def panel(prescient: bool = True, n_months: int = 24, n_tickers: int = 20) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for m in range(n_months):
        date = (pd.Timestamp(2023, 1, 2) + pd.DateOffset(months=m)).date()
        fwd = rng.normal(0.01, 0.05, n_tickers)
        for i in range(n_tickers):
            rows.append(
                {
                    "date": date,
                    "ticker": f"T{i}",
                    "fwd_ret": fwd[i],
                    "pred": fwd[i] if prescient else -fwd[i],
                }
            )
    return pd.DataFrame(rows)


def test_borrow_cost_reduces_net_returns() -> None:
    free = run_backtest(panel(), BacktestConfig(borrow_rate=0.0))
    costly = run_backtest(panel(), BacktestConfig(borrow_rate=0.10))
    assert (costly.period_frame["net"] < free.period_frame["net"]).all()


def test_sensitivity_covers_the_grid() -> None:
    rows = cost_sensitivity(panel(), cost_grid=[0.0, 0.01], borrow_grid=[0.0, 0.05])
    assert len(rows) == 4
    assert {r.round_trip_cost for r in rows} == {0.0, 0.01}


def test_returns_decline_monotonically_with_cost() -> None:
    rows = cost_sensitivity(panel(), cost_grid=[0.0, 0.002, 0.01], borrow_grid=[0.0])
    returns = [r.annual_return for r in rows]
    assert returns == sorted(returns, reverse=True)


def test_breakeven_is_the_highest_profitable_cost() -> None:
    rows = cost_sensitivity(panel(), cost_grid=[0.0, 0.001, 0.5], borrow_grid=[0.0])
    be = breakeven_cost(rows)
    assert be is not None
    assert be < 0.5  # a 50% round trip must destroy any edge


def test_no_edge_reports_no_breakeven() -> None:
    rows = cost_sensitivity(panel(prescient=False), cost_grid=[0.0, 0.01], borrow_grid=[0.0])
    assert breakeven_cost(rows) is None


def test_default_config_now_charges_borrow() -> None:
    assert BacktestConfig().borrow_rate == pytest.approx(0.01)
