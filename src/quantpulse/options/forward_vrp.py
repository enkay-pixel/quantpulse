"""Implied volatility against the volatility that then arrived: the forward variance risk premium.

Implements `docs/findings/forward-variance-risk-premium.md`. Each row of
`analytics.fct_iv_vs_forward_realized` holds one ticker's implied volatility on a snapshot day and
the realized volatility of its next 21 sessions, both annualized. The headline is the mean of the
daily cross-sectional means, with an error that allows for each day's window overlapping the next
twenty — fifty tickers on one day share the market's volatility, and consecutive days share most of
their window, so neither the ticker-days nor the days are independent.
"""

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from quantpulse.ml.metrics import newey_west_se

HORIZON = 21
ONE_SIDED_Z = 1.645
#: Plausible bounds for a single stock's annualized volatility. A mean outside them is a units
#: error — one series daily, the other annual — and nothing is read.
UNITS_RANGE = (0.05, 1.5)


def last_snapshot(sessions: list[dt.date], as_of: dt.date, horizon: int = HORIZON) -> dt.date:
    """The newest snapshot whose next `horizon` sessions had all closed by `as_of`."""
    ordered = sorted(sessions)
    if as_of not in ordered:
        raise ValueError(f"as_of {as_of} is not a trading session")
    i = ordered.index(as_of)
    if i < horizon:
        raise ValueError("no snapshot's window has closed by as_of")
    return ordered[i - horizon]


def units_ok(mean_forward_vol: float) -> bool:
    low, high = UNITS_RANGE
    return low < mean_forward_vol < high


def read(day_means: pd.Series, horizon: int = HORIZON) -> dict[str, Any]:
    """The pre-registered reading of the daily mean premiums, oldest day first."""
    values = day_means.sort_index().to_numpy(dtype=float)
    n = len(values)
    if n < 2:
        return {"state": "too_few_days", "days": n}
    mean = float(values.mean())
    se = newey_west_se(values.tolist(), max_lag=horizon - 1)
    lower, upper = mean - ONE_SIDED_Z * se, mean + ONE_SIDED_Z * se
    if lower > 0:
        state = "priced_above"
    elif upper < 0:
        state = "priced_below"
    else:
        state = "not_resolved"
    # Days the same mean would need for its bound to clear zero, if the error shrinks as one over
    # the square root of the sample. Only meaningful while unresolved.
    needed = n * (ONE_SIDED_Z * se / abs(mean)) ** 2 if state == "not_resolved" and mean else None
    return {
        "state": state,
        "days": n,
        "mean": mean,
        "std_error": se,
        "lower_bound": lower,
        "upper_bound": upper,
        "days_needed": needed,
    }


def summarize(rows: pd.DataFrame) -> dict[str, Any]:
    """Everything the finding reports, from the mart's rows for the window."""
    mean_forward_vol = float(rows["forward_realized_vol_21d"].mean())
    out: dict[str, Any] = {
        "rows": len(rows),
        "tickers": int(rows["ticker"].nunique()),
        "first": str(rows["snapshot_date"].min()),
        "last": str(rows["snapshot_date"].max()),
        "mean_atm_iv": float(rows["atm_iv"].mean()),
        "mean_forward_vol": mean_forward_vol,
        "mean_trailing_vol": float(rows["trailing_realized_vol_21d"].mean()),
        "units_ok": units_ok(mean_forward_vol),
    }
    if not out["units_ok"]:
        return out
    by_day = rows.groupby("snapshot_date")
    out["headline"] = read(by_day["forward_premium"].mean())
    out["ticker_day_mean"] = float(rows["forward_premium"].mean())
    out["trailing_premium_same_rows"] = float(rows["trailing_premium"].mean())
    # Which forecast came closer to the volatility that arrived.
    arrived = rows["forward_realized_vol_21d"]
    out["mae_implied"] = float(np.abs(rows["atm_iv"] - arrived).mean())
    out["mae_trailing"] = float(np.abs(rows["trailing_realized_vol_21d"] - arrived).mean())
    return out


def forward_vrp(
    engine: Engine, as_of: dt.date, first: dt.date, exchange: str = "XNYS"
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """The window's rows and their reading. Rows after the last closed window are excluded, so a
    later run with more data answers the same question."""
    from quantpulse.data.calendar import trading_days

    last = last_snapshot(trading_days(first, as_of, exchange), as_of)
    query = text(
        """
        SELECT ticker, snapshot_date, atm_iv, atm_days, forward_realized_vol_21d,
               trailing_realized_vol_21d, forward_premium, trailing_premium
        FROM analytics.fct_iv_vs_forward_realized
        WHERE exchange = :exchange AND snapshot_date BETWEEN :first AND :last
        ORDER BY snapshot_date, ticker
        """
    )
    params: dict[str, str | dt.date] = {"exchange": exchange, "first": first, "last": last}
    with engine.connect() as conn:
        rows = pd.read_sql(query, conn, params=params)
    return rows, summarize(rows)
