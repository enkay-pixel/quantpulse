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
    exchange: str
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
    # The thresholds the verdict is judged against, served so the page states the same numbers
    # the monitor uses rather than a copy that can drift from them.
    psi_threshold: float
    share_threshold: float


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


class IvTermPoint(BaseModel):
    """At-the-money IV at one maturity, for the latest snapshot."""

    days_to_expiry: int
    expiry: dt.date
    avg_iv: float
    n_contracts: int


class IvHistoryPoint(BaseModel):
    """At-the-money IV near the 30-day mark, one snapshot."""

    snapshot_date: dt.date
    avg_iv: float


class IvSurfaceOut(BaseModel):
    ticker: str
    snapshot_date: dt.date | None
    term_structure: list[IvTermPoint]
    history: list[IvHistoryPoint]


class ChampionRecord(BaseModel):
    """One deployed model's live record, apart from the market's."""

    model_version: str
    n_days: int
    #: Null until the model has scored a live session. A champion promoted on a non-trading
    #: day holds the alias with no record at all, and omitting it would leave the card
    #: showing only withdrawn models with nothing marking the one actually running.
    start_date: dt.date | None
    end_date: dt.date | None
    total_return: float | None
    avg_daily_return: float | None
    max_drawdown: float | None
    sharpe: float | None
    win_rate: float | None
    #: Holds the most recent live day. Decided by date, not version number.
    is_current: bool


class ChampionRecordOut(BaseModel):
    champions: list[ChampionRecord]


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
    #: Uncertainty on the alpha estimate. Alpha quoted without it is a point estimate
    #: presented as a measurement, and over a short window the error exceeds the estimate.
    alpha_std_error_annualized: float | None
    #: Alpha over its standard error. Below ~2 in absolute value the window has not
    #: separated the alpha from zero, whatever the headline number reads.
    alpha_t_stat: float | None
    r_squared: float | None
    correlation: float | None
    tracking_error: float | None
    information_ratio: float | None


class AlphaBetaOut(BaseModel):
    phases: list[AlphaBetaStats]


class DecisionConditionOut(BaseModel):
    type: str
    #: fired | armed | unknown | manual
    state: str
    detail: str


class DecisionOut(BaseModel):
    """A standing decision and whether anything has reopened it."""

    id: str
    title: str
    decided: dt.date
    note: str | None
    #: reopened (a condition fired) | unknown (one cannot be checked here) | standing | manual
    state: str
    conditions: list[DecisionConditionOut]


class DecisionsOut(BaseModel):
    decisions: list[DecisionOut]


class FindingOut(BaseModel):
    title: str
    url: str
    question: str
    outcome: str


class FindingsOut(BaseModel):
    findings: list[FindingOut]


class ForwardVrpDay(BaseModel):
    """One snapshot day: implied volatility against what then arrived, averaged over tickers."""

    snapshot_date: dt.date
    tickers: int
    implied: float
    realized: float
    premium: float


class ForwardVrpOut(BaseModel):
    exchange: str
    days: list[ForwardVrpDay]


class PositioningRow(BaseModel):
    """One ticker's positioning on the latest chain snapshot (ADR 0007).

    Gamma figures are the stock a hedger would trade per 1% move if a dealer were on the other
    side of every live contract — an upper bound, calls and puts never netted. Short interest is
    the latest figure known now, with its settlement date and the date it became known.
    """

    ticker: str
    asset_type: str
    followed_by: str = "model"
    spot: float
    call_oi: int
    put_oi: int
    call_gamma_usd_1pct: float
    put_gamma_usd_1pct: float
    call_gamma_near_share: float | None
    adv_usd_20d: float | None
    call_gamma_share_of_adv: float | None
    put_gamma_share_of_adv: float | None
    short_settlement_date: dt.date | None
    short_known_from: dt.date | None
    shares_short: int | None
    short_pct_float: float | None
    days_to_cover: float | None
    short_change: float | None


class PositioningOut(BaseModel):
    exchange: str
    snapshot_date: dt.date | None
    rows: list[PositioningRow]


class GammaStrike(BaseModel):
    strike: float
    call_oi: int
    put_oi: int
    call_gamma_usd_1pct: float
    put_gamma_usd_1pct: float


class GammaProfileOut(BaseModel):
    ticker: str
    snapshot_date: dt.date | None
    spot: float | None
    strikes: list[GammaStrike]


class AttentionRow(BaseModel):
    """One stock's public attention on its newest day (ADR 0007): the past week's mean Wikipedia
    views against the median of the 90 days before it."""

    ticker: str
    followed_by: str = "model"
    article: str
    date: dt.date
    views_7d: float
    baseline_90d: float | None
    attention_ratio: float | None


class AttentionOut(BaseModel):
    exchange: str
    as_of: dt.date | None
    rows: list[AttentionRow]


class WatchlistName(BaseModel):
    """A name the research branch follows that the model does not (ADR 0007)."""

    ticker: str
    exchange: str
    asset_type: str
    why: str
    wikipedia: str | None


class WatchlistOut(BaseModel):
    names: list[WatchlistName]


class OwnershipRow(BaseModel):
    """One US stock's insider trading over 90 days and its holders over 5% (ADR 0007), from SEC
    EDGAR. Open-market trades only: grants, exercises and tax withholding are pay, not decisions."""

    ticker: str
    followed_by: str = "model"
    bought_usd_90d: float
    sold_usd_90d: float
    buyers_90d: int
    sellers_90d: int
    planned_sold_share_90d: float | None
    last_trade_date: dt.date | None
    holders_over_5pct: int
    activist_holder: bool
    top_holder: str | None
    top_holder_percent: float | None
    top_holder_class: str | None


class OwnershipOut(BaseModel):
    exchange: str
    as_of: dt.date | None
    rows: list[OwnershipRow]


class InsiderTrade(BaseModel):
    """One open-market trade by an insider, as reported on Form 4."""

    transaction_date: dt.date
    filed: dt.date
    owner: str
    role: str
    trade: str  # 'bought' | 'sold'
    shares_traded: float
    trade_price: float
    value_usd: float
    planned: bool | None


class HolderStake(BaseModel):
    """A holder whose latest Schedule 13D or 13G still reports 5% or more."""

    filer: str
    form: str
    filed: dt.date
    shares_held: float | None
    percent: float
    share_class: str | None


class OwnershipDetailOut(BaseModel):
    ticker: str
    trades: list[InsiderTrade]
    holders: list[HolderStake]


class BriefName(BaseModel):
    ticker: str
    name: str | None
    followed_by: str


class BriefIndexOut(BaseModel):
    exchange: str
    names: list[BriefName]


class BriefFact(BaseModel):
    fact: str
    value: str
    note: str | None


class BriefOut(BaseModel):
    """One stock's advisor brief (ADR 0007): the public evidence set out for a conversation with a
    licensed advisor. Filled from numbers by fixed rules; it assesses and never advises."""

    ticker: str
    name: str | None
    exchange: str
    followed_by: str
    as_of: dt.date | None
    summary: str
    facts: list[BriefFact]
    for_points: list[str]
    against_points: list[str]
    risks: list[str]
    questions: list[str]
    limits: list[str]
    disclaimer: str


class AttentionDay(BaseModel):
    date: dt.date
    views: int
    views_7d: float
    baseline_90d: float | None


class AttentionHistoryOut(BaseModel):
    ticker: str
    article: str | None
    days: list[AttentionDay]


class OptionBookDayOut(BaseModel):
    date: dt.date
    equity: float
    phase: str
    share_equity: float | None


class OptionBookCohortOut(BaseModel):
    opened: dt.date
    exit_date: dt.date | None
    phase: str
    spreads: int
    skipped: int
    options_return: float | None
    return_on_premium: float | None
    shares_return: float | None


class OptionBookPositionOut(BaseModel):
    ticker: str
    side: str
    status: str
    note: str | None
    option_type: str | None
    expiry: dt.date | None
    long_strike: float | None
    short_strike: float | None
    entry_debit: float | None
    mark_value: float | None
    mark_basis: str | None
    mark_date: dt.date | None
    return_on_premium: float | None


class OptionBookOut(BaseModel):
    """The paper options book (ADR 0008): its value day by day beside the share book it shadows,
    each cohort's result, and the newest cohort's spreads — skipped names included, with why."""

    exchange: str
    live_since: dt.date
    risk_budget: float
    days: list[OptionBookDayOut]
    cohorts: list[OptionBookCohortOut]
    positions: list[OptionBookPositionOut]


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


class ExchangeOut(BaseModel):
    """One market the dashboard can switch to."""

    code: str
    timezone: str
    currency: str
    benchmark: str
    has_options: bool
    display_symbol: str
    display_divisor: float
    configured: bool  # has active tickers, not merely defined in the registry


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
