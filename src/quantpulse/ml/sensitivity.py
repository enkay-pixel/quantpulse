"""Cost sensitivity: at what trading cost does the strategy stop working?

A backtest is only as honest as its cost model. The headline run charges a modest
round-trip cost and a nominal borrow fee; this sweeps both so the result is stated as a
*range* rather than a single optimistic number. If the edge only survives at
unrealistically low costs, that is the finding.
"""

from dataclasses import dataclass, replace

import pandas as pd

from quantpulse.ml.backtest import BacktestConfig, run_backtest

# Round-trip cost per unit turnover (commission + slippage combined), from
# frictionless through to a deliberately punitive level.
DEFAULT_COST_GRID = [0.0, 0.0005, 0.001, 0.002, 0.005, 0.01]
DEFAULT_BORROW_GRID = [0.0, 0.01, 0.03]


@dataclass(frozen=True)
class SensitivityRow:
    round_trip_cost: float
    borrow_rate: float
    annual_return: float
    sharpe: float
    max_drawdown: float


def cost_sensitivity(
    panel: pd.DataFrame,
    base: BacktestConfig | None = None,
    cost_grid: list[float] | None = None,
    borrow_grid: list[float] | None = None,
) -> list[SensitivityRow]:
    """Run the backtest across the cost/borrow grid. `panel` needs date, ticker, pred, fwd_ret."""
    base = base or BacktestConfig()
    rows: list[SensitivityRow] = []
    for cost in cost_grid or DEFAULT_COST_GRID:
        for borrow in borrow_grid or DEFAULT_BORROW_GRID:
            cfg = replace(
                base,
                transaction_cost=cost / 2,  # split across the round trip
                slippage=cost / 2,
                borrow_rate=borrow,
            )
            stats = run_backtest(panel, cfg).stats
            rows.append(
                SensitivityRow(
                    round_trip_cost=cost,
                    borrow_rate=borrow,
                    annual_return=stats.get("annual_return", float("nan")),
                    sharpe=stats.get("sharpe", float("nan")),
                    max_drawdown=stats.get("max_drawdown", float("nan")),
                )
            )
    return rows


def breakeven_cost(rows: list[SensitivityRow], borrow_rate: float = 0.0) -> float | None:
    """Highest round-trip cost at which the strategy still earns a positive return.

    Three outcomes, and the distinction matters:

    - a cost inside the grid — the sweep bracketed the breakeven;
    - ``None`` — never profitable, so there is no edge to erode;
    - ``inf`` — still profitable at the most punitive cost tested, meaning the sweep
      never found the breakeven at all. Returning the grid ceiling here (the previous
      behaviour) silently reported "the last thing we tried" as if it were a measured
      limit, which understates the result and reads as a finding it isn't.
    """
    at_borrow = [r for r in rows if r.borrow_rate == borrow_rate]
    viable = [r.round_trip_cost for r in at_borrow if r.annual_return > 0]
    if not viable:
        return None
    if max(viable) >= max(r.round_trip_cost for r in at_borrow):
        return float("inf")
    return max(viable)
