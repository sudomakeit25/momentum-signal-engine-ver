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
