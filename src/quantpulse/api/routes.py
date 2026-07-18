import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from quantpulse.api import schemas
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.db import (
    DriftMetric,
    ModelRun,
    PortfolioSnapshot,
    Prediction,
    Price,
    UniverseMember,
)
from quantpulse.ml.metrics import TRADING_DAYS_PER_YEAR, max_drawdown, sharpe_ratio

router = APIRouter()

SessionDep = Annotated[Session, Depends(session_dep)]
EngineDep = Annotated[Engine, Depends(engine_dep)]


@router.get("/health", response_model=schemas.Health)
def health(engine: EngineDep) -> schemas.Health:
    try:
        with engine.connect() as conn:
            latest = conn.execute(text("SELECT max(date) FROM prices")).scalar()
        return schemas.Health(status="ok", database=True, latest_price_date=latest)
    except Exception:
        return schemas.Health(status="degraded", database=False, latest_price_date=None)


@router.get("/universe", response_model=list[schemas.UniverseMemberOut])
def universe(session: SessionDep) -> list[schemas.UniverseMemberOut]:
    members = session.scalars(select(UniverseMember).order_by(UniverseMember.ticker)).all()
    return [
        schemas.UniverseMemberOut(ticker=m.ticker, asset_type=m.asset_type, active=m.active)
        for m in members
    ]


@router.get("/prices/{ticker}", response_model=schemas.PriceSeries)
def prices(
    ticker: str,
    session: SessionDep,
    start: Annotated[dt.date | None, Query()] = None,
    end: Annotated[dt.date | None, Query()] = None,
) -> schemas.PriceSeries:
    ticker = ticker.upper()
    stmt = select(Price).where(Price.ticker == ticker).order_by(Price.date)
    if start:
        stmt = stmt.where(Price.date >= start)
    if end:
        stmt = stmt.where(Price.date <= end)
    rows = session.scalars(stmt).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No prices stored for {ticker}")
    points = [
        schemas.PricePoint(
            date=r.date, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume
        )
        for r in rows
    ]
    return schemas.PriceSeries(ticker=ticker, points=points)


@router.get("/predictions/latest", response_model=schemas.PredictionsOut)
def latest_predictions(session: SessionDep) -> schemas.PredictionsOut:
    latest_date = session.scalar(select(func.max(Prediction.date)))
    if latest_date is None:
        return schemas.PredictionsOut(date=None, model_version=None, rows=[])
    latest_version = session.scalar(
        select(func.max(Prediction.model_version)).where(Prediction.date == latest_date)
    )
    rows = session.scalars(
        select(Prediction)
        .where(Prediction.date == latest_date, Prediction.model_version == latest_version)
        .order_by(Prediction.score.desc())
    ).all()
    return schemas.PredictionsOut(
        date=latest_date,
        model_version=latest_version,
        rows=[
            schemas.PredictionRow(ticker=r.ticker, score=r.score, rank=i + 1)
            for i, r in enumerate(rows)
        ],
    )


@router.get("/portfolio/equity-curve", response_model=schemas.EquityCurve)
def equity_curve(session: SessionDep) -> schemas.EquityCurve:
    rows = session.scalars(select(PortfolioSnapshot).order_by(PortfolioSnapshot.date)).all()
    if not rows:
        return schemas.EquityCurve(points=[], total_return=None, max_drawdown=None, sharpe=None)
    import pandas as pd

    returns = pd.Series([r.daily_return for r in rows])
    return schemas.EquityCurve(
        points=[
            schemas.EquityPoint(
                date=r.date, equity=r.equity, daily_return=r.daily_return, turnover=r.turnover
            )
            for r in rows
        ],
        total_return=rows[-1].equity - 1.0,
        max_drawdown=max_drawdown(returns),
        sharpe=sharpe_ratio(returns, TRADING_DAYS_PER_YEAR) if len(returns) > 2 else None,
    )


@router.get("/models/current", response_model=schemas.ModelInfo)
def current_model(session: SessionDep) -> schemas.ModelInfo:
    run = session.scalars(
        select(ModelRun).where(ModelRun.decision == "promoted").order_by(ModelRun.id.desc())
    ).first()
    if run is None:
        return schemas.ModelInfo(
            model_version=None, decision=None, trained_at=None, metrics={}, mlflow_run_id=None
        )
    return schemas.ModelInfo(
        model_version=run.model_version,
        decision=run.decision,
        trained_at=run.created_at,
        metrics={k: float(v) for k, v in run.metrics.items()},
        mlflow_run_id=run.mlflow_run_id,
    )


@router.get("/drift/latest", response_model=schemas.DriftStatus)
def latest_drift(session: SessionDep) -> schemas.DriftStatus:
    latest_date = session.scalar(select(func.max(DriftMetric.date)))
    if latest_date is None:
        return schemas.DriftStatus(date=None, share_drifted=None, drifted=None, features=[])
    rows = session.scalars(select(DriftMetric).where(DriftMetric.date == latest_date)).all()
    share = next((r for r in rows if r.metric_name == "share_drifted"), None)
    features = [
        schemas.DriftFeatureOut(
            feature=r.metric_name.removeprefix("psi:"), psi=r.value, drifted=r.drifted
        )
        for r in rows
        if r.metric_name.startswith("psi:")
    ]
    return schemas.DriftStatus(
        date=latest_date,
        share_drifted=share.value if share else None,
        drifted=share.drifted if share else None,
        features=sorted(features, key=lambda f: f.psi, reverse=True),
    )


@router.get("/freshness", response_model=schemas.FreshnessOut)
def freshness(session: SessionDep) -> schemas.FreshnessOut:
    from quantpulse.db import Feature

    return schemas.FreshnessOut(
        latest_price_date=session.scalar(select(func.max(Price.date))),
        latest_feature_date=session.scalar(select(func.max(Feature.date))),
        latest_prediction_date=session.scalar(select(func.max(Prediction.date))),
        latest_snapshot_date=session.scalar(select(func.max(PortfolioSnapshot.date))),
    )
