"""Vectorized long/short quantile backtest over prediction panels.

Positions form at each rebalance from prediction quantiles; the realized period
return is the equal-weighted spread of forward returns, net of linear costs.
"""

from dataclasses import dataclass
from typing import cast

import pandas as pd

from quantpulse.ml.metrics import MONTHS_PER_YEAR, summarize_returns


@dataclass(frozen=True)
class BacktestConfig:
    long_quantile: float = 0.2
    short_quantile: float = 0.2
    transaction_cost: float = 0.0005  # one-way, per unit of turnover
    slippage: float = 0.0005
    # Shorting is not free: brokers charge an annualized borrow fee on the short leg.
    # ~1%/yr is typical for liquid large caps; hard-to-borrow names cost far more.
    borrow_rate: float = 0.01
    short_weight: float = 0.5  # capital share per side; 0.5/0.5 is a dollar-neutral book
    rebalance_freq: str = "M"  # pandas *period* alias: monthly
    min_names_per_period: int = 10


@dataclass(frozen=True)
class BacktestResult:
    period_frame: pd.DataFrame  # index: period end; columns: gross, net, turnover, equity
    stats: dict[str, float]


def run_backtest(panel: pd.DataFrame, config: BacktestConfig | None = None) -> BacktestResult:
    """`panel` needs columns: date, ticker, pred, fwd_ret (non-overlapping horizon assumed
    to roughly match the rebalance frequency)."""
    cfg = config or BacktestConfig()
    df = panel[["date", "ticker", "pred", "fwd_ret"]].copy()
    df["period"] = pd.PeriodIndex(pd.to_datetime(df["date"]), freq=cfg.rebalance_freq)

    rows = []
    prev_weights: dict[str, float] = {}
    for period_key, group in df.groupby("period"):
        period = cast(pd.Period, period_key)
        # Rebalance decisions use only the first date of each period.
        first_date = group["date"].min()
        snapshot = group[group["date"] == first_date]
        if len(snapshot) < cfg.min_names_per_period:
            continue
        long_thr = snapshot["pred"].quantile(1 - cfg.long_quantile)
        short_thr = snapshot["pred"].quantile(cfg.short_quantile)
        longs = snapshot[snapshot["pred"] >= long_thr]
        shorts = snapshot[snapshot["pred"] <= short_thr]
        if longs.empty or shorts.empty:
            continue
        gross = float(longs["fwd_ret"].mean() - shorts["fwd_ret"].mean()) / 2
        # Capital weights: half the book long, half short (gross exposure 1.0) — exactly
        # the convention the `gross` spread above assumes.
        weights = {t: cfg.short_weight / len(longs) for t in longs["ticker"]} | {
            t: -cfg.short_weight / len(shorts) for t in shorts["ticker"]
        }
        # One-way turnover: half the summed absolute weight change. Rotating into a
        # disjoint book costs 1.0; holding the same names costs 0. Charging a flat
        # quantile width here (the previous shortcut) made costs blind to churn.
        turnover = (
            sum(
                abs(weights.get(t, 0.0) - prev_weights.get(t, 0.0))
                for t in set(weights) | set(prev_weights)
            )
            / 2
        )
        prev_weights = weights
        # Borrow accrues over the holding period, not per trade.
        borrow = cfg.borrow_rate * cfg.short_weight / MONTHS_PER_YEAR
        net = gross - (cfg.transaction_cost + cfg.slippage) * turnover - borrow
        rows.append(
            {
                "period": period.to_timestamp(how="end").normalize(),
                "gross": gross,
                "net": net,
                "turnover": turnover,
                "n_long": len(longs),
                "n_short": len(shorts),
            }
        )

    if not rows:
        empty = pd.DataFrame(columns=["gross", "net", "turnover", "equity"])
        return BacktestResult(empty, {"sharpe": float("nan"), "n_periods": 0.0})

    frame = pd.DataFrame(rows).set_index("period").sort_index()
    frame["equity"] = (1 + frame["net"]).cumprod()
    stats = summarize_returns(frame["net"], MONTHS_PER_YEAR)
    return BacktestResult(frame, stats)
