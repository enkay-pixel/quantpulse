"""Score one registered model forward against the standing competitor, on sessions it never saw.

Implements `docs/findings/champion-vs-momentum.md`. A model's holdout is where it was chosen, so its
own record there cannot say how it does on new data. Everything after that holdout can: the model
was fixed before those labels existed. This scores the model and the gate's standing competitor
on the same sessions and tickers, pairs them per session, and reads a one-sided bound each way.

The model's scores are replayed from features rebuilt from stored prices. Two checks say whether the
replay is the model that ran: re-scoring its own holdout must reproduce the holdout IC its training
run recorded, and the replay must match the scores it actually served while it was live. The
served-only comparison is reported beside the replayed one, so the replay never has to be trusted
alone.
"""

import datetime as dt
import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import text
from sqlalchemy.engine import Engine

from quantpulse.features.engineering import FEATURE_COLUMNS
from quantpulse.ml.baselines import BASELINES, STANDING_COMPETITOR
from quantpulse.ml.metrics import information_coefficient, newey_west_se
from quantpulse.ml.training import HOLDOUT_FRACTION, TrainConfig, split_by_date

logger = logging.getLogger(__name__)

ONE_SIDED_Z = 1.645
#: How close the replayed holdout IC must be to the recorded one for the replay to be that model.
#: The fit is deterministic given the panel, so this only absorbs the last bits of floating point.
REPRODUCTION_TOLERANCE = 1e-6


def forward_bounds(
    sessions: list[dt.date], data_end: dt.date, as_of: dt.date, horizon: int
) -> tuple[dt.date, dt.date, dt.date]:
    """The model's holdout end, and the first and last sessions of its forward window.

    A label at session *t* is the return to *t + horizon* sessions, so a model fitted on data ending
    at `data_end` saw no label later than `horizon` sessions before it: that is the end of its
    holdout. The forward window is every session after that whose label had matured by `as_of`.
    """
    ordered = sorted(sessions)
    for name, day in (("data_end", data_end), ("as_of", as_of)):
        if day not in ordered:
            raise ValueError(f"{name} {day} is not a trading session of this market")
    i, j = ordered.index(data_end), ordered.index(as_of)
    if i < horizon:
        raise ValueError("the model's data ends before any label could have matured")
    if j - horizon <= i - horizon:
        raise ValueError("no forward session has matured by as_of")
    return ordered[i - horizon], ordered[i - horizon + 1], ordered[j - horizon]


def daily_ic(frame: pd.DataFrame, score: str) -> pd.Series:
    """Per-session rank IC of `score` against the realised return, NaN where it is undefined.

    The same per-date values `information_coefficient` averages, kept as a series so that two
    signals can be paired session by session instead of compared as two means.
    """
    out: dict[Any, float] = {}
    for date, group in frame.groupby("date"):
        if len(group) < 3 or group[score].nunique() < 2 or group["fwd_ret"].nunique() < 2:
            out[date] = float("nan")
            continue
        out[date] = float(stats.spearmanr(group[score], group["fwd_ret"]).statistic)
    return pd.Series(out, dtype=float).sort_index()


def compare(model_ic: pd.Series, competitor_ic: pd.Series, horizon: int) -> dict[str, Any]:
    """Pair two per-session IC series and read the pre-registered rule.

    A session where either IC is undefined is dropped from both, so the difference is always taken
    over the same sessions. The error allows for each label overlapping the next `horizon - 1`.
    """
    paired = pd.DataFrame({"model": model_ic, "competitor": competitor_ic}).dropna()
    diffs = (paired["model"] - paired["competitor"]).tolist()
    n = len(diffs)
    result: dict[str, Any] = {
        "sessions": n,
        "model_ic": float(paired["model"].mean()) if n else float("nan"),
        "competitor_ic": float(paired["competitor"].mean()) if n else float("nan"),
    }
    if n < 2:
        return {**result, "state": "too_few_sessions"}
    mean = float(np.mean(diffs))
    se = newey_west_se(diffs, max_lag=horizon - 1)
    lower, upper = mean - ONE_SIDED_Z * se, mean + ONE_SIDED_Z * se
    if upper < 0:
        state = "competitor_ahead"
    elif lower > 0:
        state = "model_ahead"
    else:
        state = "not_resolved"
    # The sessions the same mean would need for its bound to clear zero, if the error keeps
    # shrinking as one over the square root of the sample. Only meaningful while unresolved.
    needed = n * (ONE_SIDED_Z * se / abs(mean)) ** 2 if state == "not_resolved" and mean else None
    blocks = [
        float(np.mean(diffs[k : k + horizon]))
        for k in range(0, n, horizon)
        if diffs[k : k + horizon]
    ]
    return {
        **result,
        "state": state,
        "mean_delta": mean,
        "std_error": se,
        "lower_bound": lower,
        "upper_bound": upper,
        "sessions_needed": needed,
        "block_deltas": blocks,
    }


def served_scores(
    engine: Engine, exchange: str, version: str, first: dt.date, last: dt.date
) -> pd.DataFrame:
    """The scores a model version actually served on this market inside the window."""
    query = text(
        """
        SELECT p.ticker, p.date, p.score AS served
        FROM predictions p JOIN universe u USING (ticker)
        WHERE u.exchange = :exchange AND p.model_version = :version
          AND p.date BETWEEN :first AND :last
        """
    )
    params: dict[str, str | dt.date] = {
        "exchange": exchange,
        "version": version,
        "first": first,
        "last": last,
    }
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=params)


def champion_forward(
    engine: Engine,
    exchange: str,
    version: str,
    data_end: dt.date,
    as_of: dt.date,
    cfg: TrainConfig | None = None,
) -> pd.DataFrame:
    """Per-session ICs for one model version and the standing competitor, with the reading attached.

    Returns one row per forward session; `attrs` carries the window, both reproduction checks, the
    replayed comparison and the served-only one.
    """
    import mlflow.lightgbm
    from mlflow import MlflowClient

    from quantpulse.features.store import load_price_bars
    from quantpulse.ml.pipeline import build_dataset
    from quantpulse.ml.registry import model_name, predict_with

    cfg = cfg or TrainConfig()
    horizon = cfg.horizon_days
    sessions = sorted(load_price_bars(engine, exchange=exchange)["date"].unique())
    holdout_end, first, last = forward_bounds(sessions, data_end, as_of, horizon)

    name = model_name(exchange)
    client = MlflowClient()
    run_id = client.get_model_version(name, version).run_id
    if not run_id:
        raise ValueError(f"{name} v{version} has no training run, so its holdout IC is unknown")
    recorded_holdout_ic = client.get_run(run_id).data.metrics.get("holdout_ic")
    booster = mlflow.lightgbm.load_model(f"models:/{name}/{version}")

    full = build_dataset(engine, cfg, exchange)

    # Re-scoring the holdout the reconstructed window implies must give back the recorded score.
    _, holdout = split_by_date(
        full[full["date"] <= holdout_end], HOLDOUT_FRACTION, cfg.embargo_days
    )
    holdout["pred"] = predict_with(booster, holdout)
    replayed_holdout_ic = information_coefficient(holdout)
    reproduced = recorded_holdout_ic is not None and (
        abs(replayed_holdout_ic - recorded_holdout_ic) <= REPRODUCTION_TOLERANCE
    )

    window = full[(full["date"] >= first) & (full["date"] <= last)].copy()
    window["model"] = predict_with(booster, window)
    window["competitor"] = BASELINES[STANDING_COMPETITOR](window, window, list(FEATURE_COLUMNS))

    served = served_scores(engine, exchange, version, first, last)
    live = window.merge(served, on=["ticker", "date"], how="inner")
    replay_gap = float((live["model"] - live["served"]).abs().max()) if len(live) else float("nan")

    series = pd.DataFrame(
        {
            "model_ic": daily_ic(window, "model"),
            "competitor_ic": daily_ic(window, "competitor"),
            "served_ic": daily_ic(live, "served") if len(live) else pd.Series(dtype=float),
            "served_competitor_ic": (
                daily_ic(live, "competitor") if len(live) else pd.Series(dtype=float)
            ),
        }
    )
    series.index.name = "date"
    series.attrs = {
        "exchange": exchange,
        "version": version,
        "competitor": STANDING_COMPETITOR,
        "data_end": str(data_end),
        "as_of": str(as_of),
        "holdout_end": str(holdout_end),
        "first": str(first),
        "last": str(last),
        "recorded_holdout_ic": recorded_holdout_ic,
        "replayed_holdout_ic": replayed_holdout_ic,
        "holdout_reproduced": bool(reproduced),
        "served_rows": len(live),
        "served_sessions": int(live["date"].nunique()) if len(live) else 0,
        "max_replay_gap": replay_gap,
        "replayed": compare(series["model_ic"], series["competitor_ic"], horizon),
        "served": compare(series["served_ic"], series["served_competitor_ic"], horizon),
    }
    return series
