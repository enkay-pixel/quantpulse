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
