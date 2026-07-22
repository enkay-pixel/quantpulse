"""Simulated long/short paper books built from stored predictions.

Positions form from score quantiles and earn each day's realized return. Two books
run over the same predictions and differ in **exactly one** dimension — how often
they rebalance:

- ``daily``   — re-forms the book every day, betting the signal on tomorrow.
- ``horizon`` — re-forms every 21 trading days, the horizon the model is trained to
  forecast, and holds in between.

Keeping both is the point. The daily book asks "what if I trade this aggressively?";
the horizon book asks "what does the thing the model actually predicts earn?" The gap
between them measures how fast the signal decays and what the churn costs. That
comparison is only valid because everything else — capital convention, cost model,
borrow, quantile widths — is shared, so nothing else can explain the difference.

Capital convention matches `ml.backtest`: each side carries `SIDE_WEIGHT` of capital
(gross exposure 1.0), which is what the halved long-minus-short spread assumes.
"""

import logging
from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantpulse.db import PortfolioSnapshot
from quantpulse.ml.metrics import TRADING_DAYS_PER_YEAR

logger = logging.getLogger(__name__)

LONG_Q = 0.2
SHORT_Q = 0.2
COST_PER_TURNOVER = 0.001  # combined commission + slippage, applied on position changes
SIDE_WEIGHT = 0.5  # capital per side; 0.5/0.5 is dollar-neutral, gross exposure 1.0
BORROW_RATE = 0.01  # annualized fee on the short leg, accrued daily


@dataclass(frozen=True)
class BookConfig:
    """One paper-book construction. Only `rebalance_days` should differ between books."""

    variant: str
    rebalance_days: int
    long_q: float = LONG_Q
    short_q: float = SHORT_Q
    cost_per_turnover: float = COST_PER_TURNOVER
    borrow_rate: float = BORROW_RATE
    side_weight: float = SIDE_WEIGHT


DAILY_BOOK = BookConfig(variant="daily", rebalance_days=1)
HORIZON_BOOK = BookConfig(variant="horizon", rebalance_days=21)
BOOKS = (DAILY_BOOK, HORIZON_BOOK)


def _load_frames(engine: Engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    preds = pd.read_sql(
        # If several model versions scored the same date, keep the newest.
        "SELECT DISTINCT ON (ticker, date) ticker, date, model_version, score "
        "FROM predictions ORDER BY ticker, date, model_version DESC",
        engine,
    )
    prices = pd.read_sql("SELECT ticker, date, close FROM prices ORDER BY ticker, date", engine)
    return preds, prices


def _form_positions(group: pd.DataFrame, cfg: BookConfig) -> dict[str, float] | None:
    """Equal-weight long/short book from score quantiles, or None if a side is empty."""
    long_thr = group["score"].quantile(1 - cfg.long_q)
    short_thr = group["score"].quantile(cfg.short_q)
    longs = group[group["score"] >= long_thr]["ticker"].tolist()
    shorts = group[group["score"] <= short_thr]["ticker"].tolist()
    if not longs or not shorts:
        return None
    return {t: cfg.side_weight / len(longs) for t in longs} | {
        t: -cfg.side_weight / len(shorts) for t in shorts
    }


def build_book(
    preds: pd.DataFrame, prices: pd.DataFrame, cfg: BookConfig
) -> list[dict[str, object]]:
    """Walk the prediction dates, rebalancing every `cfg.rebalance_days`, and return
    one snapshot per day. Held days trade nothing and so pay no turnover cost."""
    # pivot (not pivot_table) so duplicate (date, ticker) keys raise instead of aggregating
    returns = prices.pivot(index="date", columns="ticker", values="close").sort_index()
    daily_ret = returns.pct_change(fill_method=None).shift(-1)  # next-day realized return

    snapshots: list[dict[str, object]] = []
    equity = 1.0
    positions: dict[str, float] = {}
    since_rebalance = 0
    # Borrow is a financing cost: it accrues per calendar day held, not per trade.
    daily_borrow = cfg.borrow_rate * cfg.side_weight / TRADING_DAYS_PER_YEAR

    for date, group in preds.groupby("date"):
        if date not in daily_ret.index:
            continue
        rebalancing = not positions or since_rebalance >= cfg.rebalance_days
        if rebalancing:
            fresh = _form_positions(group, cfg)
            if fresh is None:
                continue
            prev, positions, since_rebalance = positions, fresh, 0
        else:
            prev = positions
        since_rebalance += 1

        next_rets = daily_ret.loc[date]
        rets = np.array([next_rets.get(t, np.nan) for t in positions], dtype=float)
        weights = np.array(list(positions.values()), dtype=float)
        # The final date has no next-day return, and a name can be missing a bar.
        # nansum would report those as a flat 0.0 day, so check before trusting it;
        # names that are individually missing simply contribute nothing.
        if np.isnan(rets).all():
            continue
        gross = float(np.nansum(weights * rets))

        turnover = (
            sum(abs(positions.get(t, 0.0) - prev.get(t, 0.0)) for t in set(positions) | set(prev))
            / 2
        )
        net = gross - cfg.cost_per_turnover * turnover - daily_borrow
        equity *= 1 + net

        snapshots.append(
            {
                "date": date,
                "variant": cfg.variant,
                "equity": equity,
                "daily_return": net,
                "gross_exposure": float(sum(abs(w) for w in positions.values())),
                "net_exposure": float(sum(positions.values())),
                "turnover": float(turnover),
                "positions": {t: round(w, 6) for t, w in positions.items()},
                "model_version": str(group["model_version"].iloc[0]),
            }
        )
    return snapshots


def rebuild_portfolio(
    engine: Engine, session: Session, books: tuple[BookConfig, ...] = BOOKS
) -> int:
    """Recompute every book's snapshot trail from predictions; idempotent upsert."""
    preds, prices = _load_frames(engine)
    if preds.empty or prices.empty:
        logger.info("No predictions or prices — nothing to rebuild")
        return 0

    snapshots: list[dict[str, object]] = []
    for cfg in books:
        rows = build_book(preds, prices, cfg)
        if rows:
            logger.info(
                "Book %r: %d days, final equity %.4f", cfg.variant, len(rows), rows[-1]["equity"]
            )
        snapshots.extend(rows)

    if not snapshots:
        logger.info("No realizable portfolio days yet (predictions too recent)")
        return 0

    stmt = pg_insert(PortfolioSnapshot).values(snapshots)
    stmt = stmt.on_conflict_do_update(
        index_elements=[PortfolioSnapshot.date, PortfolioSnapshot.variant],
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
    logger.info("Rebuilt %d portfolio snapshots across %d books", len(snapshots), len(books))
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
