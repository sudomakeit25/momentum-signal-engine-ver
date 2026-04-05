"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

// Signal scanners
export function useVix() { return useQuery({ queryKey: ["vix"], queryFn: () => apiFetch<Record<string, unknown>>("/signals/vix"), refetchInterval: 5 * 60_000 }); }
export function useGaps(minGap = 2) { return useQuery({ queryKey: ["gaps", minGap], queryFn: () => apiFetch<Record<string, unknown>[]>("/signals/gaps", { min_gap: minGap }) }); }
export function useUnusualVolume(minRatio = 3) { return useQuery({ queryKey: ["unusual-vol", minRatio], queryFn: () => apiFetch<Record<string, unknown>[]>("/signals/unusual-volume", { min_ratio: minRatio }) }); }
export function useShortSqueeze() { return useQuery({ queryKey: ["short-squeeze"], queryFn: () => apiFetch<Record<string, unknown>[]>("/signals/short-squeeze") }); }
export function useBollingerSqueeze() { return useQuery({ queryKey: ["bb-squeeze"], queryFn: () => apiFetch<Record<string, unknown>[]>("/signals/bollinger-squeeze") }); }
export function useMacdDivergence() { return useQuery({ queryKey: ["macd-div"], queryFn: () => apiFetch<Record<string, unknown>[]>("/signals/macd-divergence") }); }
export function useEmaCrosses() { return useQuery({ queryKey: ["ema-crosses"], queryFn: () => apiFetch<Record<string, unknown>[]>("/signals/ema-crosses") }); }
export function useAtrRanking() { return useQuery({ queryKey: ["atr-ranking"], queryFn: () => apiFetch<Record<string, unknown>[]>("/signals/atr-ranking") }); }

// Per-symbol analysis
export function useFibonacci(symbol: string) { return useQuery({ queryKey: ["fib", symbol], queryFn: () => apiFetch<Record<string, unknown>>(`/analysis/fibonacci/${symbol}`), enabled: !!symbol }); }
export function useVolumeProfile(symbol: string) { return useQuery({ queryKey: ["vol-profile", symbol], queryFn: () => apiFetch<Record<string, unknown>>(`/analysis/volume-profile/${symbol}`), enabled: !!symbol }); }
export function useIchimoku(symbol: string) { return useQuery({ queryKey: ["ichimoku", symbol], queryFn: () => apiFetch<Record<string, unknown>>(`/analysis/ichimoku/${symbol}`), enabled: !!symbol }); }
export function usePivots(symbol: string) { return useQuery({ queryKey: ["pivots", symbol], queryFn: () => apiFetch<Record<string, unknown>>(`/signals/pivots/${symbol}`), enabled: !!symbol }); }
export function useGapFill(symbol: string) { return useQuery({ queryKey: ["gap-fill", symbol], queryFn: () => apiFetch<Record<string, unknown>>(`/signals/gap-fill/${symbol}`), enabled: !!symbol }); }

// Market data
export function useInsiderAggregation() { return useQuery({ queryKey: ["insider-agg"], queryFn: () => apiFetch<Record<string, unknown>>("/market/insiders") }); }
export function useIpoCalendar() { return useQuery({ queryKey: ["ipos"], queryFn: () => apiFetch<Record<string, unknown>[]>("/market/ipos") }); }
export function useDividendCalendar() { return useQuery({ queryKey: ["dividends"], queryFn: () => apiFetch<Record<string, unknown>[]>("/market/dividends") }); }
export function useStockSplits() { return useQuery({ queryKey: ["splits"], queryFn: () => apiFetch<Record<string, unknown>[]>("/market/splits") }); }

// Portfolio analytics
export function usePortfolioAnalytics() { return useQuery({ queryKey: ["portfolio-analytics"], queryFn: () => apiFetch<Record<string, unknown>>("/portfolio/analytics"), refetchInterval: 60_000 }); }
