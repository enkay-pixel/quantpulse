import type {
  DriftStatus,
  EquityCurve,
  Freshness,
  Health,
  ModelInfo,
  ModelRunEntry,
  Positions,
  Predictions,
  PriceSeries,
  Quintiles,
  Risk,
  SignalSeries,
  TrackRecord,
  UniverseMember,
} from "./types";

export const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`${path} responded ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => getJson<Health>("/health"),
  universe: () => getJson<UniverseMember[]>("/universe"),
  prices: (ticker: string, start?: string) =>
    getJson<PriceSeries>(
      `/prices/${encodeURIComponent(ticker)}${start ? `?start=${start}` : ""}`,
    ),
  signalHistory: (ticker: string) =>
    getJson<SignalSeries>(`/signals/history/${encodeURIComponent(ticker)}`),
  latestPredictions: () => getJson<Predictions>("/predictions/latest"),
  equityCurve: () => getJson<EquityCurve>("/portfolio/equity-curve"),
  currentModel: () => getJson<ModelInfo>("/models/current"),
  latestDrift: () => getJson<DriftStatus>("/drift/latest"),
  freshness: () => getJson<Freshness>("/freshness"),
  trackRecord: () => getJson<TrackRecord>("/track-record"),
  quintiles: () => getJson<Quintiles>("/signals/quintiles"),
  risk: () => getJson<Risk>("/portfolio/risk"),
  positions: () => getJson<Positions>("/portfolio/positions"),
  modelHistory: () => getJson<ModelRunEntry[]>("/models/history"),
};
