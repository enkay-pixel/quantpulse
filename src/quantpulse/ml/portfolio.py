"""Simulated long/short paper book built from stored predictions.

For every date with predictions, form an equal-weight long/short portfolio from
score quantiles and realize the next trading day's return. This is the "live"
performance trail shown on the dashboard (distinct from the training backtest).
"""

import logging
from typing import cast

import numpy as np
import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantpulse.db import PortfolioSnapshot

logger = logging.getLogger(__name__)

LONG_Q = 0.2
SHORT_Q = 0.2
COST_PER_TURNOVER = 0.001  # combined commission + slippage, applied on position changes


def _load_frames(engine: Engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    preds = pd.read_sql(
        # If several model versions scored the same date, keep the newest.
        "SELECT DISTINCT ON (ticker, date) ticker, date, model_version, score "
        "FROM predictions ORDER BY ticker, date, model_version DESC",
        engine,
    )
    prices = pd.read_sql("SELECT ticker, date, close FROM prices ORDER BY ticker, date", engine)
    return preds, prices


def rebuild_portfolio(engine: Engine, session: Session) -> int:
    """Recompute the whole snapshot trail from predictions; idempotent upsert."""
    preds, prices = _load_frames(engine)
    if preds.empty or prices.empty:
        logger.info("No predictions or prices — nothing to rebuild")
        return 0

    # pivot (not pivot_table) so duplicate (date, ticker) keys raise instead of aggregating
    returns = prices.pivot(index="date", columns="ticker", values="close").sort_index()
    daily_ret = returns.pct_change(fill_method=None).shift(-1)  # next-day realized return

    snapshots: list[dict[str, object]] = []
    equity = 1.0
    prev_positions: dict[str, float] = {}
    for date, group in preds.groupby("date"):
        if date not in daily_ret.index:
            continue
        long_thr = group["score"].quantile(1 - LONG_Q)
        short_thr = group["score"].quantile(SHORT_Q)
        longs = group[group["score"] >= long_thr]["ticker"].tolist()
        shorts = group[group["score"] <= short_thr]["ticker"].tolist()
        if not longs or not shorts:
            continue
        positions = {t: 1.0 / len(longs) for t in longs} | {t: -1.0 / len(shorts) for t in shorts}

        next_rets = daily_ret.loc[date]
        long_ret = float(np.nanmean([next_rets.get(t, np.nan) for t in longs]))
        short_ret = float(np.nanmean([next_rets.get(t, np.nan) for t in shorts]))
        if np.isnan(long_ret) or np.isnan(short_ret):
            continue
        gross = (long_ret - short_ret) / 2

        all_names = set(positions) | set(prev_positions)
        turnover = (
            sum(abs(positions.get(t, 0.0) - prev_positions.get(t, 0.0)) for t in all_names) / 2
        )
        net = gross - COST_PER_TURNOVER * turnover
        equity *= 1 + net
        prev_positions = positions

        snapshots.append(
            {
                "date": date,
                "equity": equity,
                "daily_return": net,
                "gross_exposure": float(sum(abs(w) for w in positions.values())),
                "net_exposure": float(sum(positions.values())),
                "turnover": float(turnover),
                "positions": {t: round(w, 6) for t, w in positions.items()},
                "model_version": str(group["model_version"].iloc[0]),
            }
        )

    if not snapshots:
        logger.info("No realizable portfolio days yet (predictions too recent)")
        return 0

    stmt = pg_insert(PortfolioSnapshot).values(snapshots)
    stmt = stmt.on_conflict_do_update(
        index_elements=[PortfolioSnapshot.date],
        set_={
            col: getattr(stmt.excluded, col)
            for col in (
                "equity",
                "daily_return",
                "gross_exposure",
                "net_exposure",
                "turnover",
                "positions",
                "model_version",
            )
        },
    )
    session.execute(stmt)
    logger.info("Rebuilt %d portfolio snapshots (final equity %.4f)", len(snapshots), equity)
    return len(snapshots)


def score_history(
    engine: Engine,
    session: Session,
    tracking_uri: str | None = None,
) -> int:
    """Replay the champion over all stored feature dates (marked by its model version).

    Useful to seed the dashboard with a signal trail; dates inside the champion's
    training window are in-sample and labeled as a replay, not a live track record.
    """
    from quantpulse.db import Prediction
    from quantpulse.features.engineering import FEATURE_COLUMNS, FEATURE_VERSION
    from quantpulse.features.store import load_features
    from quantpulse.ml import registry

    if tracking_uri:
        registry.configure(tracking_uri)
    loaded = registry.load_champion()
    if loaded is None:
        logger.warning("No champion model — cannot replay history")
        return 0
    booster, champion = loaded
    features = load_features(engine, FEATURE_VERSION)
    if features.empty:
        return 0
    features = features.copy()
    features["score"] = np.asarray(booster.predict(features[list(FEATURE_COLUMNS)]))
    records = [
        {
            "ticker": cast(str, row["ticker"]),
            "date": row["date"],
            "model_version": str(champion.version),
            "score": float(row["score"]),
        }
        for row in features.to_dict(orient="records")
    ]
    from quantpulse.utils import chunked

    for chunk in chunked(records):
        stmt = pg_insert(Prediction).values(list(chunk))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Prediction.ticker, Prediction.date, Prediction.model_version],
            set_={"score": stmt.excluded.score},
        )
        session.execute(stmt)
    logger.info("Replayed champion v%s over %d rows", champion.version, len(records))
    return len(records)
