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

export interface Freshness {
  latest_price_date: string | null;
  latest_feature_date: string | null;
  latest_prediction_date: string | null;
  latest_snapshot_date: string | null;
}
