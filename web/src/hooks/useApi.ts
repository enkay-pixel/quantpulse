import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

const REFRESH_MS = 60_000; // dashboards refresh themselves once a minute

export const useExchanges = () =>
  useQuery({ queryKey: ["exchanges"], queryFn: api.exchanges, staleTime: Infinity });

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: REFRESH_MS });

export const usePredictions = () =>
  useQuery({
    queryKey: ["predictions"],
    queryFn: api.latestPredictions,
    refetchInterval: REFRESH_MS,
  });

export const useEquityCurve = (exchange: string) =>
  useQuery({
    queryKey: ["equity", exchange],
    queryFn: () => api.equityCurve(exchange),
    refetchInterval: REFRESH_MS,
  });

export const useCurrentModel = () =>
  useQuery({ queryKey: ["model"], queryFn: api.currentModel, refetchInterval: REFRESH_MS });

export const useDrift = () =>
  useQuery({ queryKey: ["drift"], queryFn: api.latestDrift, refetchInterval: REFRESH_MS });

export const useFreshness = (exchange: string) =>
  useQuery({
    queryKey: ["freshness", exchange],
    queryFn: () => api.freshness(exchange),
    refetchInterval: REFRESH_MS,
  });

export const useTrackRecord = (exchange: string) =>
  useQuery({
    queryKey: ["track-record", exchange],
    queryFn: () => api.trackRecord(exchange),
    refetchInterval: REFRESH_MS,
  });

export const useAlphaBeta = (exchange: string) =>
  useQuery({
    queryKey: ["alpha-beta", exchange],
    queryFn: () => api.alphaBeta(exchange),
    refetchInterval: REFRESH_MS,
  });

export const useBooks = (exchange: string) =>
  useQuery({
    queryKey: ["books", exchange],
    queryFn: () => api.books(exchange),
    refetchInterval: REFRESH_MS,
  });

export const useQuintiles = (exchange: string) =>
  useQuery({
    queryKey: ["quintiles", exchange],
    queryFn: () => api.quintiles(exchange),
    refetchInterval: REFRESH_MS,
  });

export const useRisk = (exchange: string) =>
  useQuery({
    queryKey: ["risk", exchange],
    queryFn: () => api.risk(exchange),
    refetchInterval: REFRESH_MS,
  });

export const usePositions = (exchange: string) =>
  useQuery({
    queryKey: ["positions", exchange],
    queryFn: () => api.positions(exchange),
    refetchInterval: REFRESH_MS,
  });

export const useModelHistory = (exchange: string) =>
  useQuery({
    queryKey: ["model-history", exchange],
    queryFn: () => api.modelHistory(exchange),
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
