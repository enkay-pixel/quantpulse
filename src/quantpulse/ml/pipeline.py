"""End-to-end ML pipeline steps: train/evaluate/promote and daily scoring.

These are the library entrypoints that Dagster assets (and the CLI) call; they own
the glue between the feature store, LightGBM training, MLflow, and Postgres audit rows.
"""

import datetime as dt
import logging

import numpy as np
import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantpulse.data.calendar import DEFAULT_EXCHANGE, get_exchange
from quantpulse.db import ModelRun, Prediction
from quantpulse.features.engineering import (
    FEATURE_COLUMNS,
    FEATURE_VERSION,
    build_training_frame,
    compute_features,
    make_forward_returns,
)
from quantpulse.features.store import load_features, load_price_bars
from quantpulse.ml import registry
from quantpulse.ml.backtest import BacktestConfig, run_backtest
from quantpulse.ml.metrics import information_coefficient
from quantpulse.ml.promotion import decide_promotion
from quantpulse.ml.training import TrainConfig, train_final_model, tune_hyperparameters

logger = logging.getLogger(__name__)


def build_dataset(
    engine: Engine, cfg: TrainConfig, exchange: str = DEFAULT_EXCHANGE
) -> pd.DataFrame:
    """Assemble one market's training frame from stored bars: features + forward returns."""
    bars = load_price_bars(engine, exchange=exchange)
    if bars.empty:
        raise ValueError(f"No price bars for {exchange} — run ingestion first")
    features = compute_features(bars)
    targets = make_forward_returns(bars, cfg.horizon_days)
    frame = build_training_frame(features, targets)
    if frame.empty:
        raise ValueError("Training frame is empty — not enough history for the horizon")
    return frame


def _score_holdout(holdout: pd.DataFrame, width: float) -> dict[str, float]:
    """One scoring rule for every model the gate compares — candidate and incumbent."""
    backtest = run_backtest(holdout, BacktestConfig(long_quantile=width, short_quantile=width))
    return {
        "holdout_ic": information_coefficient(holdout),
        "holdout_sharpe": backtest.stats.get("sharpe", float("nan")),
        "holdout_max_drawdown": backtest.stats.get("max_drawdown", float("nan")),
        "holdout_annual_return": backtest.stats.get("annual_return", float("nan")),
    }


def train_evaluate_promote(
    engine: Engine,
    session: Session,
    cfg: TrainConfig | None = None,
    tracking_uri: str | None = None,
    exchange: str = DEFAULT_EXCHANGE,
) -> dict[str, object]:
    """The self-adapting loop's training half, for one market. Summary for logging/UI."""
    cfg = cfg or TrainConfig()
    if tracking_uri:
        registry.configure(tracking_uri)

    frame = build_dataset(engine, cfg, exchange)
    feature_cols = list(FEATURE_COLUMNS)

    params = tune_hyperparameters(frame, feature_cols, cfg)
    booster, holdout = train_final_model(frame, feature_cols, params, cfg)

    # The gate must measure the construction the market actually runs: judging a 20%
    # book while the JSE trades a 35% one would promote on evidence about a portfolio
    # that does not exist.
    width = get_exchange(exchange).quantile_width
    candidate_metrics = _score_holdout(holdout, width)

    version = registry.log_candidate(
        booster, params, candidate_metrics, feature_cols, FEATURE_VERSION, exchange=exchange
    )
    # Both models sit the SAME exam: the incumbent is re-scored on this run's holdout
    # under this run's code, never trusted from its stored metrics. Stored numbers go
    # stale whenever the evaluation code or the panel changes — incident 24: a backfill
    # grew the panel, the fractional cut slid 9 months into a momentum-rich stretch, and
    # a candidate "beat" an incumbent that had been examined on a different window.
    champion = registry.load_champion(exchange=exchange)
    incumbent_metrics = None
    if champion is not None:
        champ_booster, _ = champion
        rescored = holdout.copy()
        rescored["pred"] = np.asarray(champ_booster.predict(rescored[feature_cols]))
        incumbent_metrics = _score_holdout(rescored, width)
        logger.info(
            "%s incumbent re-scored on candidate's holdout: sharpe=%.3f ic=%.4f",
            exchange,
            incumbent_metrics["holdout_sharpe"],
            incumbent_metrics["holdout_ic"],
        )
    decision = decide_promotion(candidate_metrics, incumbent_metrics)
    if decision.promote:
        registry.promote(version.version, exchange=exchange)

    # The exam window goes in the audit row: a holdout defined as a fraction of the panel
    # moves when the panel grows, and a moved exam must be visible, not archaeology.
    window = {
        "holdout_start": str(holdout["date"].min()),
        "holdout_end": str(holdout["date"].max()),
        "holdout_days": int(holdout["date"].nunique()),
    }
    session.add(
        ModelRun(
            run_type="train",
            exchange=exchange,
            mlflow_run_id=version.run_id,
            model_version=str(version.version),
            metrics={**{k: v for k, v in candidate_metrics.items() if v == v}, **window},
            decision="promoted" if decision.promote else "rejected",
        )
    )
    logger.info(
        "%s training complete: version=%s promoted=%s (%s)",
        exchange,
        version.version,
        decision.promote,
        decision.reason,
    )
    return {
        "exchange": exchange,
        "model_version": str(version.version),
        "promoted": decision.promote,
        "reason": decision.reason,
        **candidate_metrics,
    }


def score_latest(
    engine: Engine,
    session: Session,
    asof: dt.date | None = None,
    tracking_uri: str | None = None,
    exchange: str = DEFAULT_EXCHANGE,
) -> int:
    """Score one market's most recent feature date with its champion; upsert predictions."""
    if tracking_uri:
        registry.configure(tracking_uri)
    loaded = registry.load_champion(exchange)
    if loaded is None:
        logger.warning("No champion model for %s — skipping scoring", exchange)
        return 0
    booster, champion = loaded

    features = load_features(engine, FEATURE_VERSION, start=None, end=asof, exchange=exchange)
    if features.empty:
        logger.warning("No stored features to score for %s", exchange)
        return 0
    latest_date = features["date"].max()
    latest = features[features["date"] == latest_date].copy()
    latest["score"] = np.asarray(booster.predict(latest[list(FEATURE_COLUMNS)]))

    records = [
        {
            "ticker": row["ticker"],
            "date": row["date"],
            "model_version": str(champion.version),
            "score": float(row["score"]),
        }
        for row in latest.to_dict(orient="records")
    ]
    stmt = pg_insert(Prediction).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Prediction.ticker, Prediction.date, Prediction.model_version],
        set_={"score": stmt.excluded.score},
    )
    session.execute(stmt)
    logger.info(
        "Scored %d tickers for %s with model v%s", len(records), latest_date, champion.version
    )
    return len(records)
