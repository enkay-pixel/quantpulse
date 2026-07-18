"""Response models. Every endpoint returns one of these — nothing ad-hoc."""

import datetime as dt

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    database: bool
    latest_price_date: dt.date | None


class UniverseMemberOut(BaseModel):
    ticker: str
    asset_type: str
    active: bool


class PricePoint(BaseModel):
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceSeries(BaseModel):
    ticker: str
    points: list[PricePoint]


class PredictionRow(BaseModel):
    ticker: str
    score: float
    rank: int


class PredictionsOut(BaseModel):
    date: dt.date | None
    model_version: str | None
    rows: list[PredictionRow]


class EquityPoint(BaseModel):
    date: dt.date
    equity: float
    daily_return: float
    turnover: float


class EquityCurve(BaseModel):
    points: list[EquityPoint]
    total_return: float | None
    max_drawdown: float | None
    sharpe: float | None


class ModelInfo(BaseModel):
    model_version: str | None
    decision: str | None
    trained_at: dt.datetime | None
    metrics: dict[str, float]
    mlflow_run_id: str | None


class DriftFeatureOut(BaseModel):
    feature: str
    psi: float
    drifted: bool


class DriftStatus(BaseModel):
    date: dt.date | None
    share_drifted: float | None
    drifted: bool | None
    features: list[DriftFeatureOut]


class FreshnessOut(BaseModel):
    latest_price_date: dt.date | None
    latest_feature_date: dt.date | None
    latest_prediction_date: dt.date | None
    latest_snapshot_date: dt.date | None
