"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { ChartData } from "@/types/api";
import { CHART_REFRESH_MS } from "@/lib/constants";

export function useChartData(symbol: string, days = 200) {
  return useQuery({
    queryKey: ["chart", symbol, days],
    queryFn: () =>
      apiFetch<ChartData>(`/chart/${symbol}`, { days }),
    enabled: !!symbol,
    refetchInterval: CHART_REFRESH_MS,
  });
}
