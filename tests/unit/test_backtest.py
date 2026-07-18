import numpy as np
import pandas as pd

from quantpulse.ml.backtest import BacktestConfig, BacktestResult, run_backtest


def make_panel(prescient: bool, n_months: int = 12, n_tickers: int = 20) -> pd.DataFrame:
    """Monthly snapshots where fwd_ret spreads are known; prescient preds equal fwd_ret."""
    rng = np.random.default_rng(11)
    rows = []
    for m in range(n_months):
        date = pd.Timestamp(2023, 1, 2) + pd.DateOffset(months=m)
        fwd = rng.normal(0.01, 0.05, n_tickers)
        for i in range(n_tickers):
            rows.append(
                {
                    "date": date.date(),
                    "ticker": f"T{i}",
                    "fwd_ret": fwd[i],
                    "pred": fwd[i] if prescient else -fwd[i],
                }
            )
    return pd.DataFrame(rows)


def test_prescient_predictions_win() -> None:
    result = run_backtest(make_panel(prescient=True))
    assert isinstance(result, BacktestResult)
    assert (result.period_frame["gross"] > 0).all()
    assert result.stats["sharpe"] > 1


def test_inverted_predictions_lose() -> None:
    result = run_backtest(make_panel(prescient=False))
    assert (result.period_frame["gross"] < 0).all()


def test_costs_reduce_net() -> None:
    panel = make_panel(prescient=True)
    free = run_backtest(panel, BacktestConfig(transaction_cost=0.0, slippage=0.0))
    costly = run_backtest(panel, BacktestConfig(transaction_cost=0.01, slippage=0.01))
    assert (costly.period_frame["net"] < free.period_frame["net"]).all()


def test_thin_universe_produces_empty_result() -> None:
    panel = make_panel(prescient=True, n_tickers=3)
    result = run_backtest(panel, BacktestConfig(min_names_per_period=10))
    assert result.period_frame.empty
    assert result.stats["n_periods"] == 0.0


def test_equity_curve_compounds() -> None:
    result = run_backtest(make_panel(prescient=True))
    expected = (1 + result.period_frame["net"]).cumprod()
    pd.testing.assert_series_equal(result.period_frame["equity"], expected, check_names=False)
