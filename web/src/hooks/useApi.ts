import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

const REFRESH_MS = 60_000; // dashboards refresh themselves once a minute

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: REFRESH_MS });

export const usePredictions = () =>
  useQuery({
    queryKey: ["predictions"],
    queryFn: api.latestPredictions,
    refetchInterval: REFRESH_MS,
  });

export const useEquityCurve = () =>
  useQuery({ queryKey: ["equity"], queryFn: api.equityCurve, refetchInterval: REFRESH_MS });

export const useCurrentModel = () =>
  useQuery({ queryKey: ["model"], queryFn: api.currentModel, refetchInterval: REFRESH_MS });

export const useDrift = () =>
  useQuery({ queryKey: ["drift"], queryFn: api.latestDrift, refetchInterval: REFRESH_MS });

export const useFreshness = () =>
  useQuery({ queryKey: ["freshness"], queryFn: api.freshness, refetchInterval: REFRESH_MS });

export const useTrackRecord = () =>
  useQuery({ queryKey: ["track-record"], queryFn: api.trackRecord, refetchInterval: REFRESH_MS });

export const useAlphaBeta = () =>
  useQuery({ queryKey: ["alpha-beta"], queryFn: api.alphaBeta, refetchInterval: REFRESH_MS });

export const useBooks = () =>
  useQuery({ queryKey: ["books"], queryFn: api.books, refetchInterval: REFRESH_MS });

export const useQuintiles = () =>
  useQuery({ queryKey: ["quintiles"], queryFn: api.quintiles, refetchInterval: REFRESH_MS });

export const useRisk = () =>
  useQuery({ queryKey: ["risk"], queryFn: api.risk, refetchInterval: REFRESH_MS });

export const usePositions = () =>
  useQuery({ queryKey: ["positions"], queryFn: api.positions, refetchInterval: REFRESH_MS });

export const useModelHistory = () =>
  useQuery({
    queryKey: ["model-history"],
    queryFn: api.modelHistory,
    refetchInterval: REFRESH_MS,
  });

export const usePrices = (ticker: string | null) =>
  useQuery({
    queryKey: ["prices", ticker],
    queryFn: () => api.prices(ticker as string),
    enabled: ticker !== null,
  });

export const useOptionSummary = (ticker: string | null) =>
  useQuery({
    queryKey: ["option-summary", ticker],
    queryFn: () => api.optionSummary(ticker as string),
    enabled: ticker !== null,
  });

export const useOptionChain = (ticker: string | null, expiry?: string) =>
  useQuery({
    queryKey: ["option-chain", ticker, expiry ?? null],
    queryFn: () => api.optionChain(ticker as string, expiry),
    enabled: ticker !== null,
  });

export const useOptionIdea = (ticker: string | null) =>
  useQuery({
    queryKey: ["option-idea", ticker],
    queryFn: () => api.optionIdea(ticker as string),
    enabled: ticker !== null,
  });

export const useSignalHistory = (ticker: string | null) =>
  useQuery({
    queryKey: ["signals", ticker],
    queryFn: () => api.signalHistory(ticker as string),
    enabled: ticker !== null,
  });
