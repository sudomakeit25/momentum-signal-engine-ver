"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

// News Sentiment
export function useNewsFeed() {
  return useQuery({
    queryKey: ["news-feed"],
    queryFn: () => apiFetch<{ market_sentiment: Record<string, unknown>; articles: Record<string, unknown>[] }>("/news/feed"),
    refetchInterval: 5 * 60_000,
  });
}

export function useNewsSentiment(symbol: string) {
  return useQuery({
    queryKey: ["news-sentiment", symbol],
    queryFn: () => apiFetch<Record<string, unknown>>(`/news/${symbol}`),
    enabled: !!symbol,
  });
}

// Sector Flow
export function useSectorFlow() {
  return useQuery({
    queryKey: ["sector-flow"],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/sectors/flow"),
    refetchInterval: 5 * 60_000,
  });
}

// Correlation
export function useCorrelationScan(days = 60) {
  return useQuery({
    queryKey: ["correlation-scan", days],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/correlation/scan", { days }),
    refetchInterval: 5 * 60_000,
  });
}

// Market Regime
export function useMarketRegime() {
  return useQuery({
    queryKey: ["market-regime"],
    queryFn: () => apiFetch<Record<string, unknown>>("/market/regime"),
    refetchInterval: 5 * 60_000,
  });
}
