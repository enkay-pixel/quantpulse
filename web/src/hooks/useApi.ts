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

export const usePrices = (ticker: string | null) =>
  useQuery({
    queryKey: ["prices", ticker],
    queryFn: () => api.prices(ticker as string),
    enabled: ticker !== null,
  });
