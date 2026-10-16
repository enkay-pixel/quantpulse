// Mirrors src/quantpulse/api/schemas.py — keep in sync with the backend.

export interface Health {
  status: string;
  database: boolean;
  latest_price_date: string | null;
}

export interface UniverseMember {
  ticker: string;
  asset_type: "stock" | "etf";
  active: boolean;
}

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface PriceSeries {
  ticker: string;
  points: PricePoint[];
}

export interface PredictionRow {
  ticker: string;
  score: number;
  rank: number;
}

export interface Predictions {
  date: string | null;
  model_version: string | null;
  rows: PredictionRow[];
}

export interface EquityPoint {
  date: string;
  equity: number;
  daily_return: number;
  turnover: number;
  phase: "replay" | "live" | null;
  benchmark_equity: number | null;
  horizon_equity: number | null;
}

export interface Exchange {
  code: string;
  timezone: string;
  currency: string;
  benchmark: string;
  has_options: boolean;
  display_symbol: string;
  display_divisor: number;
  configured: boolean;
}

export interface BookStats {
  variant: string;
  rebalance_days: number;
  n_days: number;
  total_return: number;
  annualized_return: number;
  annualized_gross_return: number;
  sharpe: number | null;
  max_drawdown: number;
  mean_turnover: number;
  annualized_cost_drag: number;
}

export interface BookComparison {
  books: BookStats[];
}

export interface EquityCurve {
  points: EquityPoint[];
  total_return: number | null;
  max_drawdown: number | null;
  sharpe: number | null;
}

export interface ModelInfo {
  model_version: string | null;
  decision: string | null;
  trained_at: string | null;
  metrics: Record<string, number>;
  mlflow_run_id: string | null;
}

export interface DriftFeature {
  feature: string;
  psi: number;
  drifted: boolean;
}

export interface DriftStatus {
  date: string | null;
  share_drifted: number | null;
  drifted: boolean | null;
  features: DriftFeature[];
  psi_threshold: number;
  share_threshold: number;
}

export interface OptionSummary {
  ticker: string;
  snapshot_date: string | null;
  underlying_close: number | null;
  atm_iv: number | null;
  atm_days: number | null;
  put_call_ratio: number | null;
  call_oi: number | null;
  put_oi: number | null;
  n_contracts: number | null;
  expiries: string[];
}

export interface OptionContract {
  expiry: string;
  strike: number;
  option_type: "call" | "put";
  bid: number | null;
  ask: number | null;
  last_price: number | null;
  volume: number;
  open_interest: number;
  implied_volatility: number;
  in_the_money: boolean;
  theo_value: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}

export interface OptionChain {
  ticker: string;
  snapshot_date: string | null;
  expiry: string | null;
  underlying_close: number | null;
  contracts: OptionContract[];
}

export interface OptionLeg {
  action: string;
  option_type: string;
  strike: number;
  price: number;
}

export interface OptionIdea {
  ticker: string;
  available: boolean;
  signal: number | null;
  direction: string | null;
  structure: string | null;
  rationale: string | null;
  expiry: string | null;
  legs: OptionLeg[];
  net_debit: number | null;
  max_profit: number | null;
  max_loss: number | null;
  breakeven: number | null;
}

export interface SignalPoint {
  date: string;
  score: number;
  model_version: string;
}

export interface SignalSeries {
  ticker: string;
  points: SignalPoint[];
}

export interface PhaseStats {
  phase: "replay" | "live";
  n_days: number;
  start_date: string;
  end_date: string;
  total_return: number;
  annualized_volatility: number | null;
  sharpe: number | null;
  max_drawdown: number | null;
  win_rate: number | null;
}

export interface TrackRecord {
  live_since: string | null;
  phases: PhaseStats[];
}

export interface IvTermPoint {
  days_to_expiry: number;
  expiry: string;
  avg_iv: number;
  n_contracts: number;
}

export interface IvHistoryPoint {
  snapshot_date: string;
  avg_iv: number;
}

export interface IvSurface {
  ticker: string;
  snapshot_date: string | null;
  term_structure: IvTermPoint[];
  history: IvHistoryPoint[];
}

export interface ChampionRecord {
  model_version: string;
  n_days: number;
  // Null until the model has scored a live session.
  start_date: string | null;
  end_date: string | null;
  total_return: number | null;
  avg_daily_return: number | null;
  max_drawdown: number | null;
  sharpe: number | null;
  win_rate: number | null;
  is_current: boolean;
}

export interface ChampionRecordOut {
  champions: ChampionRecord[];
}

export interface AlphaBetaStats {
  phase: "replay" | "live";
  n_days: number;
  beta: number | null;
  alpha_daily: number | null;
  alpha_annualized: number | null;
  alpha_std_error_annualized: number | null;
  alpha_t_stat: number | null;
  r_squared: number | null;
  correlation: number | null;
  tracking_error: number | null;
  information_ratio: number | null;
}

export interface AlphaBeta {
  phases: AlphaBetaStats[];
}

export interface QuintileStat {
  signal_quintile: number;
  n_days: number;
  avg_next_day_return: number;
}

export interface Quintiles {
  overall: QuintileStat[];
  recent: QuintileStat[];
}

export interface RiskPoint {
  date: string;
  drawdown: number;
  rolling_sharpe_63d: number | null;
}

export interface Risk {
  points: RiskPoint[];
}

export interface PositionRow {
  ticker: string;
  weight: number;
  side: "long" | "short";
  latest_close: number | null;
  latest_score: number | null;
}

export interface Positions {
  date: string | null;
  model_version: string | null;
  rows: PositionRow[];
}

export interface ModelRunEntry {
  id: number;
  run_type: string;
  model_version: string | null;
  decision: string | null;
  metrics: Record<string, number>;
  mlflow_run_id: string | null;
  created_at: string;
}

export interface Freshness {
  latest_price_date: string | null;
  latest_feature_date: string | null;
  latest_prediction_date: string | null;
  latest_snapshot_date: string | null;
}

export interface DecisionCondition {
  type: string;
  /** fired | armed | unknown | manual */
  state: string;
  detail: string;
}

export interface Decision {
  id: string;
  title: string;
  decided: string;
  note: string | null;
  /** reopened | unknown | standing | manual */
  state: string;
  conditions: DecisionCondition[];
}

export interface DecisionsOut {
  decisions: Decision[];
}

export interface Finding {
  title: string;
  url: string;
  question: string;
  outcome: string;
}

export interface FindingsOut {
  findings: Finding[];
}

export interface ForwardVrpDay {
  snapshot_date: string;
  tickers: number;
  implied: number;
  realized: number;
  premium: number;
}

export interface ForwardVrpOut {
  exchange: string;
  days: ForwardVrpDay[];
}

/** One ticker on the latest chain snapshot (ADR 0007). Gamma figures are the stock a hedger
 * would trade per 1% move if a dealer were on the other side of every live contract — an upper
 * bound, with calls and puts never netted. Short interest is the latest figure known now. */
export interface PositioningRow {
  ticker: string;
  asset_type: string;
  spot: number;
  call_oi: number;
  put_oi: number;
  call_gamma_usd_1pct: number;
  put_gamma_usd_1pct: number;
  call_gamma_near_share: number | null;
  adv_usd_20d: number | null;
  call_gamma_share_of_adv: number | null;
  put_gamma_share_of_adv: number | null;
  short_settlement_date: string | null;
  short_known_from: string | null;
  shares_short: number | null;
  short_pct_float: number | null;
  days_to_cover: number | null;
  short_change: number | null;
}

export interface PositioningOut {
  exchange: string;
  snapshot_date: string | null;
  rows: PositioningRow[];
}

export interface GammaStrike {
  strike: number;
  call_oi: number;
  put_oi: number;
  call_gamma_usd_1pct: number;
  put_gamma_usd_1pct: number;
}

export interface GammaProfileOut {
  ticker: string;
  snapshot_date: string | null;
  spot: number | null;
  strikes: GammaStrike[];
}

/** One stock's public attention on its newest day (ADR 0007): the past week's mean Wikipedia
 * views against the median of the 90 days before it. Both markets. */
export interface AttentionRow {
  ticker: string;
  article: string;
  date: string;
  views_7d: number;
  baseline_90d: number | null;
  attention_ratio: number | null;
}

export interface AttentionOut {
  exchange: string;
  as_of: string | null;
  rows: AttentionRow[];
}

export interface AttentionDay {
  date: string;
  views: number;
  views_7d: number;
  baseline_90d: number | null;
}

export interface AttentionHistoryOut {
  ticker: string;
  article: string | null;
  days: AttentionDay[];
}
