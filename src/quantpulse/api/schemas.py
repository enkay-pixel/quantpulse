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
    phase: str | None = None  # 'replay' | 'live' once the dbt marts exist
    benchmark_equity: float | None = None  # SPY buy-and-hold indexed to the same start


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


class SignalPoint(BaseModel):
    date: dt.date
    score: float
    model_version: str


class SignalSeries(BaseModel):
    ticker: str
    points: list[SignalPoint]


class PhaseStats(BaseModel):
    phase: str  # 'replay' (in-sample) | 'live' (out-of-sample)
    n_days: int
    start_date: dt.date
    end_date: dt.date
    total_return: float
    annualized_volatility: float | None
    sharpe: float | None
    max_drawdown: float | None
    win_rate: float | None


class TrackRecord(BaseModel):
    live_since: dt.date | None  # first champion promotion date
    phases: list[PhaseStats]


class QuintileStat(BaseModel):
    signal_quintile: int
    n_days: int
    avg_next_day_return: float


class QuintilesOut(BaseModel):
    overall: list[QuintileStat]
    recent: list[QuintileStat]  # trailing ~30 trading days


class RiskPoint(BaseModel):
    date: dt.date
    drawdown: float
    rolling_sharpe_63d: float | None


class RiskOut(BaseModel):
    points: list[RiskPoint]


class PositionRow(BaseModel):
    ticker: str
    weight: float
    side: str  # 'long' | 'short'
    latest_close: float | None
    latest_score: float | None


class PositionsOut(BaseModel):
    date: dt.date | None
    model_version: str | None
    rows: list[PositionRow]


class ModelRunOut(BaseModel):
    id: int
    run_type: str
    model_version: str | None
    decision: str | None
    metrics: dict[str, float]
    mlflow_run_id: str | None
    created_at: dt.datetime


class FreshnessOut(BaseModel):
    latest_price_date: dt.date | None
    latest_feature_date: dt.date | None
    latest_prediction_date: dt.date | None
    latest_snapshot_date: dt.date | None
