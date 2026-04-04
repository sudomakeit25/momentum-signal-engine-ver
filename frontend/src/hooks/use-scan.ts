"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { ScanResult } from "@/types/api";
import { SCAN_REFRESH_MS, CHART_REFRESH_MS } from "@/lib/constants";

interface ScanFilters {
  top?: number;
  min_price?: number;
  max_price?: number;
  min_volume?: number;
}

export function useScan(filters: ScanFilters = {}, autoRefresh = true) {
  return useQuery({
    queryKey: ["scan", filters],
    queryFn: () =>
      apiFetch<ScanResult[]>("/scan", filters as Record<string, number>),
    refetchInterval: autoRefresh ? SCAN_REFRESH_MS : false,
  });
}

export function useScanSymbol(symbol: string) {
  return useQuery({
    queryKey: ["scan", symbol],
    queryFn: () => apiFetch<ScanResult | null>(`/scan/${symbol}`),
    enabled: !!symbol,
    refetchInterval: CHART_REFRESH_MS,
  });
}
