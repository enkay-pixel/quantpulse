"""Response models. Every endpoint returns one of these — nothing ad-hoc."""

import datetime as dt

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    database: bool
    latest_price_date: dt.date | None
    # Self-reported footprint; null off Linux, where there is no cgroup to read.
    memory_rss_bytes: int | None = None
    memory_limit_bytes: int | None = None


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
    horizon_equity: float | None = None  # the 21-day book over the same predictions


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


class OptionSummary(BaseModel):
    ticker: str
    snapshot_date: dt.date | None
    underlying_close: float | None
    atm_iv: float | None
    atm_days: int | None
    put_call_ratio: float | None
    call_oi: int | None
    put_oi: int | None
    n_contracts: int | None
    expiries: list[dt.date]


class OptionContract(BaseModel):
    expiry: dt.date
    strike: float
    option_type: str
    bid: float | None
    ask: float | None
    last_price: float | None
    volume: int
    open_interest: int
    implied_volatility: float
    in_the_money: bool
    theo_value: float
    delta: float
    gamma: float
    theta: float
    vega: float


class OptionChainOut(BaseModel):
    ticker: str
    snapshot_date: dt.date | None
    expiry: dt.date | None
    underlying_close: float | None
    contracts: list[OptionContract]


class OptionLegOut(BaseModel):
    action: str
    option_type: str
    strike: float
    price: float


class OptionIdeaOut(BaseModel):
    """A HYPOTHETICAL illustration of the model's directional view — not advice."""

    ticker: str
    available: bool
    signal: float | None
    direction: str | None
    structure: str | None
    rationale: str | None
    expiry: dt.date | None
    legs: list[OptionLegOut]
    net_debit: float | None
    max_profit: float | None
    max_loss: float | None
    breakeven: float | None


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


class AlertEntry(BaseModel):
    timestamp: str
    job_name: str
    run_id: str
    error: str


class AlertsOut(BaseModel):
    alerts: list[AlertEntry]


class AlphaBetaStats(BaseModel):
    """CAPM decomposition vs the benchmark for one evidence phase."""

    phase: str
    n_days: int
    beta: float | None
    alpha_daily: float | None
    alpha_annualized: float | None
    r_squared: float | None
    correlation: float | None
    tracking_error: float | None
    information_ratio: float | None


class AlphaBetaOut(BaseModel):
    phases: list[AlphaBetaStats]


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


class BookStats(BaseModel):
    """One paper-book construction, summarized for side-by-side comparison."""

    variant: str
    rebalance_days: int
    n_days: int
    total_return: float
    annualized_return: float
    # Before costs, so the gap between books can be split into "picks" vs "friction"
    # rather than approximated from the cost drag.
    annualized_gross_return: float
    sharpe: float | None
    max_drawdown: float
    mean_turnover: float
    annualized_cost_drag: float  # what trading this book costs per year


class BookComparison(BaseModel):
    books: list[BookStats]


class FreshnessOut(BaseModel):
    latest_price_date: dt.date | None
    latest_feature_date: dt.date | None
    latest_prediction_date: dt.date | None
    latest_snapshot_date: dt.date | None
