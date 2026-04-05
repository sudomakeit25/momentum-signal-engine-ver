"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { DarkPoolResult } from "@/types/api";

export function useDarkPoolScan(top = 20, days = 20) {
  return useQuery({
    queryKey: ["dark-pool-scan", top, days],
    queryFn: () =>
      apiFetch<DarkPoolResult[]>("/dark-pool/scan", { top, days }),
    refetchInterval: 5 * 60_000, // 5 min
  });
}

export function useDarkPool(symbol: string, days = 20) {
  return useQuery({
    queryKey: ["dark-pool", symbol, days],
    queryFn: () =>
      apiFetch<DarkPoolResult>(`/dark-pool/${symbol}`, { days }),
    enabled: !!symbol,
  });
}
