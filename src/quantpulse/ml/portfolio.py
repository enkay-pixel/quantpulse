"""Simulated paper books built from stored predictions.

Positions form from score quantiles and earn each day's realized return. Several books run
over the same predictions, per exchange, as **variations from one baseline** — each
differing from it in exactly one dimension, so the gap between a variation and the baseline
is attributable to that dimension and nothing else:

- ``daily`` (baseline) — re-forms every day, betting the signal on tomorrow.
- ``horizon``   — varies ``rebalance_days`` (1 → 21), the horizon the model is trained to
  forecast. Isolates what trading more often costs.
- ``long_only`` — varies ``short_enabled``. Isolates what the short leg contributes, and is
  the only construction executable where scrip lending is thin or dear (e.g. the JSE).

Keeping all of them is the point: one book cannot tell you why it performed as it did.
Note that two *variations* are not comparable to each other — they differ in two things.
Compare each to the baseline.

Capital convention matches `ml.backtest`: gross exposure 1.0 in every book. Long/short
splits it `SIDE_WEIGHT` per side and nets to zero market exposure; long-only puts all of it
in the top quantile and is fully exposed by construction. Books never mix exchanges, so
they never mix currencies or sessions.
"""

import logging
from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantpulse.data.calendar import DEFAULT_EXCHANGE
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
    """One paper-book construction.

    Books are **variations from a shared baseline**, each differing from it in exactly one
    dimension — that is what makes the gap between a variation and the baseline
    attributable to that dimension and nothing else. Two *variations* are not comparable to
    each other (they differ in two things); compare each to the baseline.
    """

    variant: str
    rebalance_days: int
    long_q: float = LONG_Q
    short_q: float = SHORT_Q
    cost_per_turnover: float = COST_PER_TURNOVER
    borrow_rate: float = BORROW_RATE
    side_weight: float = SIDE_WEIGHT
    short_enabled: bool = True
    # Which field this book varies from the baseline; None marks the baseline itself.
    varies: str | None = None


#: The reference construction every variation is measured against.
DAILY_BOOK = BookConfig(variant="daily", rebalance_days=1)

#: Isolates what trading more often costs — the only change is how often it rebalances.
HORIZON_BOOK = BookConfig(variant="horizon", rebalance_days=21, varies="rebalance_days")

#: Isolates what the short leg contributes. Also the only construction an investor could
#: actually execute where scrip lending is thin or dear (e.g. the JSE).
LONG_ONLY_BOOK = BookConfig(
    variant="long_only", rebalance_days=1, short_enabled=False, varies="short_enabled"
)

BOOKS = (DAILY_BOOK, HORIZON_BOOK, LONG_ONLY_BOOK)
BASELINE = DAILY_BOOK


def _load_frames(engine: Engine, exchange: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predictions and prices for one market. Books never mix currencies or sessions."""
    preds = pd.read_sql(
        # If several model versions scored the same date, keep the newest.
        "SELECT DISTINCT ON (p.ticker, p.date) p.ticker, p.date, p.model_version, p.score "
        "FROM predictions p JOIN universe u ON u.ticker = p.ticker AND u.exchange = %(ex)s "
        "ORDER BY p.ticker, p.date, p.model_version DESC",
        engine,
        params={"ex": exchange},
    )
    prices = pd.read_sql(
        "SELECT p.ticker, p.date, p.close FROM prices p "
        "JOIN universe u ON u.ticker = p.ticker AND u.exchange = %(ex)s "
        "ORDER BY p.ticker, p.date",
        engine,
        params={"ex": exchange},
    )
    return preds, prices


def _form_positions(group: pd.DataFrame, cfg: BookConfig) -> dict[str, float] | None:
    """Equal-weight book from score quantiles, or None if a required side is empty.

    Both constructions deploy the same gross capital (1.0), so their returns are
    comparable: long/short splits it 0.5 per side and nets to zero market exposure;
    long-only puts all of it in the top quantile and is fully exposed by construction.
    That exposure difference is the thing being measured, not a confound.
    """
    long_thr = group["score"].quantile(1 - cfg.long_q)
    longs = group[group["score"] >= long_thr]["ticker"].tolist()
    if not longs:
        return None
    if not cfg.short_enabled:
        return {t: 1.0 / len(longs) for t in longs}

    short_thr = group["score"].quantile(cfg.short_q)
    shorts = group[group["score"] <= short_thr]["ticker"].tolist()
    if not shorts:
        return None
    return {t: cfg.side_weight / len(longs) for t in longs} | {
        t: -cfg.side_weight / len(shorts) for t in shorts
    }


def build_book(
    preds: pd.DataFrame,
    prices: pd.DataFrame,
    cfg: BookConfig,
    exchange: str = DEFAULT_EXCHANGE,
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
    # Borrow is a financing cost on the short leg: it accrues per day held, not per trade.
    # A book with no short leg borrows nothing.
    daily_borrow = (
        cfg.borrow_rate * cfg.side_weight / TRADING_DAYS_PER_YEAR if cfg.short_enabled else 0.0
    )

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
                "exchange": exchange,
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
    engine: Engine,
    session: Session,
    books: tuple[BookConfig, ...] = BOOKS,
    exchange: str = DEFAULT_EXCHANGE,
) -> int:
    """Recompute every book's snapshot trail for one market; idempotent upsert."""
    preds, prices = _load_frames(engine, exchange)
    if preds.empty or prices.empty:
        logger.info("No predictions or prices for %s — nothing to rebuild", exchange)
        return 0

    snapshots: list[dict[str, object]] = []
    for cfg in books:
        rows = build_book(preds, prices, cfg, exchange)
        if rows:
            logger.info(
                "%s book %r: %d days, final equity %.4f",
                exchange,
                cfg.variant,
                len(rows),
                rows[-1]["equity"],
            )
        snapshots.extend(rows)

    if not snapshots:
        logger.info("No realizable portfolio days yet (predictions too recent)")
        return 0

    stmt = pg_insert(PortfolioSnapshot).values(snapshots)
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            PortfolioSnapshot.date,
            PortfolioSnapshot.exchange,
            PortfolioSnapshot.variant,
        ],
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
    exchange: str = DEFAULT_EXCHANGE,
) -> int:
    """Replay one market's champion over its own stored feature dates.

    Useful to seed the dashboard with a signal trail; dates inside the champion's
    training window are in-sample and labeled as a replay, not a live track record.

    Scoped to one exchange in both directions: this market's champion, this market's
    features. Scoring every market with one champion would write predictions a model
    was never trained for.
    """
    from quantpulse.db import Prediction
    from quantpulse.features.engineering import FEATURE_COLUMNS, FEATURE_VERSION
    from quantpulse.features.store import load_features
    from quantpulse.ml import registry

    if tracking_uri:
        registry.configure(tracking_uri)
    loaded = registry.load_champion(exchange)
    if loaded is None:
        logger.warning("No champion model for %s — cannot replay history", exchange)
        return 0
    booster, champion = loaded
    features = load_features(engine, FEATURE_VERSION, exchange=exchange)
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
    logger.info("Replayed %s champion v%s over %d rows", exchange, champion.version, len(records))
    return len(records)
