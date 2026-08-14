"""End-to-end ML pipeline steps: train/evaluate/promote and daily scoring.

These are the library entrypoints that Dagster assets (and the CLI) call; they own
the glue between the feature store, LightGBM training, MLflow, and Postgres audit rows.
"""

import datetime as dt
import logging

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text
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
from quantpulse.ml.baselines import STANDING_COMPETITOR, standing_competitor_metrics
from quantpulse.ml.metrics import information_coefficient
from quantpulse.ml.promotion import PromotionPolicy, decide_promotion
from quantpulse.ml.training import TrainConfig, train_final_model, tune_hyperparameters
from quantpulse.utils import chunked

logger = logging.getLogger(__name__)

#: How far back scoring looks for feature dates that were never scored. Matches the
#: catch-up sensor's ingest lookback — a session it rescues must still be scorable.
SCORING_LOOKBACK_DAYS = 30


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


def score_holdout(holdout: pd.DataFrame, width: float) -> dict[str, float]:
    """One scoring rule for every model that is compared — candidate, incumbent, baseline.

    Public so `ml/baselines.py` sits the *same* exam rather than a copy of it. A second
    implementation of the scoring rule is the shape of bug this session spent a day fixing:
    two things that agree with each other and disagree with the thing being measured."""
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
    candidate_metrics = score_holdout(holdout, width)

    version = registry.log_candidate(
        booster, params, candidate_metrics, feature_cols, FEATURE_VERSION, exchange=exchange
    )
    # Both models sit the SAME exam: the incumbent is re-scored on this run's holdout
    # under this run's code, never trusted from its stored metrics. Stored numbers go stale
    # whenever the evaluation code or the panel changes: the holdout is a fraction of the
    # panel, so a backfill slides the window, and a candidate can "beat" an incumbent that
    # was examined on different data.
    champion = registry.load_champion(exchange=exchange)
    incumbent_metrics = None
    if champion is not None:
        champ_booster, _ = champion
        rescored = holdout.copy()
        rescored["pred"] = np.asarray(champ_booster.predict(rescored[feature_cols]))
        incumbent_metrics = score_holdout(rescored, width)
        logger.info(
            "%s incumbent re-scored on candidate's holdout: sharpe=%.3f ic=%.4f",
            exchange,
            incumbent_metrics["holdout_sharpe"],
            incumbent_metrics["holdout_ic"],
        )
    # The IC margin is per-market: a thinner cross-section re-rolls wider, so the JSE needs
    # a larger difference before it means anything (see Exchange.ic_promotion_margin).
    policy = PromotionPolicy(min_ic_improvement=get_exchange(exchange).ic_promotion_margin)
    # The standing competitor sits the same exam as the other two, on the same holdout.
    # Scored every run rather than cached, for the same reason the incumbent is re-scored:
    # a stored number describes a window that has since moved.
    baseline_metrics = standing_competitor_metrics(holdout, width)
    logger.info(
        "%s %s baseline on this holdout: ic=%.4f sharpe=%.3f",
        exchange,
        STANDING_COMPETITOR,
        baseline_metrics["holdout_ic"],
        baseline_metrics["holdout_sharpe"],
    )
    decision = decide_promotion(
        candidate_metrics, incumbent_metrics, policy, baseline=baseline_metrics
    )
    if decision.promote:
        registry.promote(version.version, exchange=exchange)

    # The exam window goes in the audit row: a holdout defined as a fraction of the panel
    # moves when the panel grows, and a moved exam must be visible, not archaeology.
    window = {
        "holdout_start": str(holdout["date"].min()),
        "holdout_end": str(holdout["date"].max()),
        "holdout_days": int(holdout["date"].nunique()),
        # What the model had to beat, stored beside what it scored. Without it a rejection
        # reads as "IC 0.068" with no way to see that the bar was 0.117.
        f"baseline_{STANDING_COMPETITOR}_ic": round(baseline_metrics["holdout_ic"], 6),
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


def dates_with_predictions(engine: Engine, exchange: str, since: dt.date) -> set[dt.date]:
    """Dates this market already has predictions for, from *any* champion."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT p.date FROM predictions p "
                "JOIN universe u ON u.ticker = p.ticker AND u.exchange = :ex "
                "WHERE p.date >= :since"
            ),
            {"ex": exchange, "since": since},
        ).all()
    return {row.date for row in rows}


def last_scored_date(engine: Engine, exchange: str) -> dt.date | None:
    """Newest date this market has any prediction for; None on a fresh database."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT max(p.date) FROM predictions p "
                "JOIN universe u ON u.ticker = p.ticker AND u.exchange = :ex"
            ),
            {"ex": exchange},
        ).scalar()


def champion_promoted_on(engine: Engine, exchange: str, version: str) -> dt.date | None:
    """When this model version was promoted, or None if no promotion is recorded.

    The same date `fct_portfolio_daily` uses to decide `backfilled` vs `live`, so the two
    layers agree on what counts as out-of-sample. Reads the *first* promotion: a version
    demoted and later re-promoted is out-of-sample from when it first took over.
    """
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT min(created_at)::date FROM model_runs "
                "WHERE model_version = :v AND decision = 'promoted' "
                "AND (exchange = :ex OR exchange IS NULL)"
            ),
            {"v": str(version), "ex": exchange},
        ).scalar()


def scoring_window_start(engine: Engine, exchange: str, latest_feature_date: dt.date) -> dt.date:
    """Where scoring starts looking for gaps: far enough back to cover the whole outage.

    A fixed 30-day floor covers ordinary operation, but the laptop this runs on gets shut
    down for travel, and an absence longer than the floor would leave the oldest sessions
    permanently unscored, without anything failing. So the window also stretches back to the
    last date that has any prediction: whatever accumulated during the gap is filled on
    return.

    Reaching back is only safe because `fct_portfolio_daily` marks days scored by a
    champion promoted after them as **backfilled** rather than live. Without that, a long
    catch-up would quietly file in-sample predictions as out-of-sample evidence.
    """
    floor = latest_feature_date - dt.timedelta(days=SCORING_LOOKBACK_DAYS)
    last = last_scored_date(engine, exchange)
    if last is None or last >= floor:
        return floor
    logger.info(
        "%s: last scored %s, %d days before the usual floor — widening the scoring window",
        exchange,
        last,
        (floor - last).days,
    )
    return last


def score_latest(
    engine: Engine,
    session: Session,
    asof: dt.date | None = None,
    tracking_uri: str | None = None,
    exchange: str = DEFAULT_EXCHANGE,
) -> int:
    """Score one market's unscored recent feature dates with its champion; upsert.

    Not just the newest date. A session ingested late — rescued by the catch-up sensor
    after that night's process run — is never the maximum at any later scoring time, so it
    would never be scored at all: features exist, predictions do not, and the paper book
    carries a permanent hole that silently shortens the live track record — the one number
    this project asks to be judged on.

    Only dates with **no predictions from any champion** are filled in. Re-scoring a date
    some earlier champion already scored would rewrite the live record with a model that
    did not exist at the time — and invisibly, because the marts take the newest model
    version per date. The newest feature date is the deliberate exception: it is always
    re-scored (idempotently) so a freshly promoted champion's view of today lands at once.
    """
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
    window_start = scoring_window_start(engine, exchange, latest_date)
    recent = features[features["date"] >= window_start]
    pending = set(recent["date"]) - dates_with_predictions(engine, exchange, window_start)
    # The newest date is normally re-scored so a freshly promoted champion's view of today
    # lands at once — but only when the champion already existed on that date. If features
    # are stale relative to a promotion (the process job runs Mon-Fri while the retrain runs
    # Saturday, so any Monday market holiday leaves the newest feature date on Friday),
    # re-scoring would hand an already-live day to a model trained on it. The marts take the
    # newest model version per date, so that day would silently flip from `live` to
    # `backfilled` and leave the out-of-sample record. Unscored dates still fill in below
    # and are labelled `backfilled` honestly; this only protects days already scored.
    promoted_on = champion_promoted_on(engine, exchange, champion.version)
    if promoted_on is None or latest_date >= promoted_on:
        pending |= {latest_date}
    elif latest_date not in pending:
        logger.info(
            "%s: leaving %s with the model that scored it — champion v%s was only promoted "
            "on %s, so re-scoring would reclassify a live day as backfilled",
            exchange,
            latest_date,
            champion.version,
            promoted_on,
        )
    to_score = recent[recent["date"].isin(pending)].copy()
    to_score["score"] = np.asarray(booster.predict(to_score[list(FEATURE_COLUMNS)]))

    records = [
        {
            "ticker": row["ticker"],
            "date": row["date"],
            "model_version": str(champion.version),
            "score": float(row["score"]),
        }
        for row in to_score.to_dict(orient="records")
    ]
    for batch in chunked(records):
        stmt = pg_insert(Prediction).values(list(batch))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Prediction.ticker, Prediction.date, Prediction.model_version],
            set_={"score": stmt.excluded.score},
        )
        session.execute(stmt)
    backfilled = sorted(pending - {latest_date})
    logger.info(
        "Scored %d rows across %d date(s) for %s with model v%s%s",
        len(records),
        len(pending),
        exchange,
        champion.version,
        f" (backfilled {backfilled})" if backfilled else "",
    )
    return len(records)
