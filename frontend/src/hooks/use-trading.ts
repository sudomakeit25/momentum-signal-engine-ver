"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost, apiPostJson } from "@/lib/api";

export function useTradingAccount() {
  return useQuery({
    queryKey: ["trading-account"],
    queryFn: () => apiFetch<Record<string, unknown>>("/trading/account"),
    refetchInterval: 30_000,
  });
}

export function useTradingPositions() {
  return useQuery({
    queryKey: ["trading-positions"],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/trading/positions"),
    refetchInterval: 15_000,
  });
}

export function useTradingOrders(status = "open") {
  return useQuery({
    queryKey: ["trading-orders", status],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/trading/orders", { status }),
    refetchInterval: 15_000,
  });
}

export function usePlaceOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (order: { symbol: string; qty: number; side: string; order_type?: string; limit_price?: number; stop_price?: number }) =>
      apiPostJson("/trading/order", order),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trading-positions"] });
      qc.invalidateQueries({ queryKey: ["trading-orders"] });
      qc.invalidateQueries({ queryKey: ["trading-account"] });
    },
  });
}

export function useClosePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => apiPost(`/trading/close/${symbol}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trading-positions"] });
      qc.invalidateQueries({ queryKey: ["trading-account"] });
    },
  });
}

// Custom Screener
export function useCustomScan(filters: Record<string, unknown>) {
  return useQuery({
    queryKey: ["custom-scan", filters],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/screener/scan", filters as Record<string, string | number>),
  });
}

export function useScreenerFilters() {
  return useQuery({
    queryKey: ["screener-filters"],
    queryFn: () => apiFetch<Record<string, unknown>>("/screener/filters"),
  });
}

// Multi-Timeframe
export function useMultiTimeframe(symbol: string) {
  return useQuery({
    queryKey: ["multi-tf", symbol],
    queryFn: () => apiFetch<Record<string, unknown>>(`/multi-tf/${symbol}`),
    enabled: !!symbol,
  });
}

// Community
export function useCommunityFeed(limit = 50, symbol = "") {
  return useQuery({
    queryKey: ["community-feed", limit, symbol],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/community/feed", { limit, symbol: symbol || undefined }),
    refetchInterval: 30_000,
  });
}

// Options Strategy
export function useOptionsStrategies() {
  return useQuery({
    queryKey: ["options-strategies"],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/options/strategies"),
  });
}

export function useOptionsStrategy(key: string, stockPrice: number) {
  return useQuery({
    queryKey: ["options-strategy", key, stockPrice],
    queryFn: () => apiFetch<Record<string, unknown>>(`/options/strategy/${key}`, { stock_price: stockPrice }),
    enabled: !!key && stockPrice > 0,
  });
}

export function usePresetStrategies() {
  return useQuery({
    queryKey: ["screener-presets"],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/screener/presets"),
  });
}

export function usePresetScan(strategy: string, topN = 25) {
  return useQuery({
    queryKey: ["screener-preset-run", strategy, topN],
    queryFn: () => apiFetch<Record<string, unknown>>(`/screener/preset/${strategy}`, { top_n: topN }),
    enabled: !!strategy,
  });
}

export function useAnalyzer(symbol: string) {
  return useQuery({
    queryKey: ["analyzer", symbol],
    queryFn: () => apiFetch<Record<string, unknown>>(`/analyzer/${symbol}`),
    enabled: !!symbol,
  });
}

export function useMultiYearTrends(symbol: string) {
  return useQuery({
    queryKey: ["trends", symbol],
    queryFn: () => apiFetch<Record<string, unknown>>(`/trends/${symbol}`),
    enabled: !!symbol,
  });
}

export function useProfileScreenerMeta() {
  return useQuery({
    queryKey: ["profile-screener-meta"],
    queryFn: () => apiFetch<Record<string, unknown>>("/profile-screener/profiles"),
    staleTime: 60 * 60 * 1000,
  });
}

export function useProfileScreenerRun(
  params: Record<string, string | number | undefined>,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["profile-screener-run", params],
    queryFn: () => apiFetch<Record<string, unknown>>("/profile-screener/run", params),
    enabled,
    staleTime: 30 * 60 * 1000,
  });
}

export function useInstrumentFundamentals(symbol: string) {
  return useQuery({
    queryKey: ["instrument-fundamentals", symbol],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/instrument/${symbol}/fundamentals`),
    enabled: !!symbol,
    staleTime: 60 * 60 * 1000,
  });
}

export function useInstrumentSeasonality(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ["instrument-seasonality", symbol],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/instrument/${symbol}/seasonality`),
    enabled: enabled && !!symbol,
    staleTime: 60 * 60 * 1000,
  });
}

export function useInstrumentIndicators(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ["instrument-indicators", symbol],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/instrument/${symbol}/indicators`),
    enabled: enabled && !!symbol,
    staleTime: 2 * 60 * 1000,
  });
}

export function useInstrumentChart(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ["instrument-chart", symbol],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/chart/${symbol}`),
    enabled: enabled && !!symbol,
    staleTime: 5 * 60 * 1000,
  });
}

export function useInstrumentNews(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ["instrument-news", symbol],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/instrument/${symbol}/news`),
    enabled: enabled && !!symbol,
    staleTime: 10 * 60 * 1000,
  });
}

export function useTranscriptList(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ["transcripts", symbol],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/instrument/${symbol}/transcripts`),
    enabled: enabled && !!symbol,
    staleTime: 24 * 60 * 60 * 1000,
  });
}

export function useInstrumentEvents(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ["instrument-events", symbol],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/instrument/${symbol}/events`),
    enabled: enabled && !!symbol,
    staleTime: 60 * 60 * 1000,
  });
}

export function useInstrumentInsider(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ["instrument-insider", symbol],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/instrument/${symbol}/insider-trades`),
    enabled: enabled && !!symbol,
    staleTime: 60 * 60 * 1000,
  });
}

export function useMarketNews(enabled = true) {
  return useQuery({
    queryKey: ["market-news"],
    queryFn: () => apiFetch<Record<string, unknown>>("/news/feed"),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useIndustryList() {
  return useQuery({
    queryKey: ["rankings-industries"],
    queryFn: () => apiFetch<{ slug: string; label: string }[]>("/rankings/industries"),
    staleTime: 24 * 60 * 60 * 1000,
  });
}

export function useIndustryRanking(slug: string) {
  return useQuery({
    queryKey: ["industry-ranking", slug],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/rankings/industry/${slug}`),
    enabled: !!slug,
    staleTime: 24 * 60 * 60 * 1000,
  });
}

export function useCotContracts() {
  return useQuery({
    queryKey: ["cot-contracts"],
    queryFn: () => apiFetch<{ key: string; label: string }[]>("/cot/contracts"),
    staleTime: 24 * 60 * 60 * 1000,
  });
}

export function useCotContract(key: string) {
  return useQuery({
    queryKey: ["cot", key],
    queryFn: () => apiFetch<Record<string, unknown>>(`/cot/${key}`),
    enabled: !!key,
    staleTime: 12 * 60 * 60 * 1000,
  });
}

export function useSectorMap(days = 365) {
  return useQuery({
    queryKey: ["sector-map", days],
    queryFn: () =>
      apiFetch<Record<string, unknown>>("/sector-map", { days }),
    staleTime: 60 * 60 * 1000,
  });
}
