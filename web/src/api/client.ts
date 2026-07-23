import type {
  AlphaBeta,
  BookComparison,
  Exchange,
  DriftStatus,
  EquityCurve,
  Freshness,
  Health,
  ModelInfo,
  ModelRunEntry,
  OptionChain,
  OptionIdea,
  OptionSummary,
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
  latestPredictions: (ex: string) =>
    getJson<Predictions>(`/predictions/latest?exchange=${ex}`),
  currentModel: (ex: string) => getJson<ModelInfo>(`/models/current?exchange=${ex}`),
  latestDrift: () => getJson<DriftStatus>("/drift/latest"),
  exchanges: () => getJson<Exchange[]>("/exchanges"),
  // Market-scoped: the backend defaults to XNYS, but the dashboard is always explicit
  // so a switch can never silently fall back to another market's numbers.
  equityCurve: (ex: string) => getJson<EquityCurve>(`/portfolio/equity-curve?exchange=${ex}`),
  alphaBeta: (ex: string) => getJson<AlphaBeta>(`/portfolio/alpha-beta?exchange=${ex}`),
  books: (ex: string) => getJson<BookComparison>(`/portfolio/books?exchange=${ex}`),
  freshness: (ex: string) => getJson<Freshness>(`/freshness?exchange=${ex}`),
  trackRecord: (ex: string) => getJson<TrackRecord>(`/track-record?exchange=${ex}`),
  quintiles: (ex: string) => getJson<Quintiles>(`/signals/quintiles?exchange=${ex}`),
  risk: (ex: string) => getJson<Risk>(`/portfolio/risk?exchange=${ex}`),
  positions: (ex: string) => getJson<Positions>(`/portfolio/positions?exchange=${ex}`),
  modelHistory: (ex: string) => getJson<ModelRunEntry[]>(`/models/history?exchange=${ex}`),
  optionSummary: (ticker: string) =>
    getJson<OptionSummary>(`/options/${encodeURIComponent(ticker)}/summary`),
  optionChain: (ticker: string, expiry?: string) =>
    getJson<OptionChain>(
      `/options/${encodeURIComponent(ticker)}/chain${expiry ? `?expiry=${expiry}` : ""}`,
    ),
  optionIdea: (ticker: string) =>
    getJson<OptionIdea>(`/options/${encodeURIComponent(ticker)}/idea`),
};
