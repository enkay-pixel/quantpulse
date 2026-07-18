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
from quantpulse.ml.backtest import run_backtest
from quantpulse.ml.metrics import information_coefficient
from quantpulse.ml.promotion import decide_promotion
from quantpulse.ml.training import TrainConfig, train_final_model, tune_hyperparameters

logger = logging.getLogger(__name__)


def build_dataset(engine: Engine, cfg: TrainConfig) -> pd.DataFrame:
    """Assemble the training frame from stored bars: features + forward returns."""
    bars = load_price_bars(engine)
    if bars.empty:
        raise ValueError("No price bars in database — run ingestion first")
    features = compute_features(bars)
    targets = make_forward_returns(bars, cfg.horizon_days)
    frame = build_training_frame(features, targets)
    if frame.empty:
        raise ValueError("Training frame is empty — not enough history for the horizon")
    return frame


def train_evaluate_promote(
    engine: Engine,
    session: Session,
    cfg: TrainConfig | None = None,
    tracking_uri: str | None = None,
) -> dict[str, object]:
    """The self-adapting loop's training half. Returns a summary for logging/UI."""
    cfg = cfg or TrainConfig()
    if tracking_uri:
        registry.configure(tracking_uri)

    frame = build_dataset(engine, cfg)
    feature_cols = list(FEATURE_COLUMNS)

    params = tune_hyperparameters(frame, feature_cols, cfg)
    booster, holdout = train_final_model(frame, feature_cols, params, cfg)

    backtest = run_backtest(holdout)
    candidate_metrics = {
        "holdout_ic": information_coefficient(holdout),
        "holdout_sharpe": backtest.stats.get("sharpe", float("nan")),
        "holdout_max_drawdown": backtest.stats.get("max_drawdown", float("nan")),
        "holdout_annual_return": backtest.stats.get("annual_return", float("nan")),
    }

    version = registry.log_candidate(
        booster, params, candidate_metrics, feature_cols, FEATURE_VERSION
    )
    incumbent_metrics = registry.champion_metrics()
    decision = decide_promotion(candidate_metrics, incumbent_metrics)
    if decision.promote:
        registry.promote(version.version)

    session.add(
        ModelRun(
            run_type="train",
            mlflow_run_id=version.run_id,
            model_version=str(version.version),
            metrics={k: v for k, v in candidate_metrics.items() if v == v},
            decision="promoted" if decision.promote else "rejected",
        )
    )
    logger.info(
        "Training complete: version=%s promoted=%s (%s)",
        version.version,
        decision.promote,
        decision.reason,
    )
    return {
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
) -> int:
    """Score the most recent feature date with the champion; upsert predictions."""
    if tracking_uri:
        registry.configure(tracking_uri)
    loaded = registry.load_champion()
    if loaded is None:
        logger.warning("No champion model — skipping scoring")
        return 0
    booster, champion = loaded

    features = load_features(engine, FEATURE_VERSION, start=None, end=asof)
    if features.empty:
        logger.warning("No stored features to score")
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
