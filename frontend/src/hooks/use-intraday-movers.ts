"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { IntradayResult } from "@/types/api";
import { SCAN_REFRESH_MS } from "@/lib/constants";

export interface IntradayMoversFilters {
  top?: number;
  min_price?: number;
  min_avg_volume?: number;
  min_change_pct?: number;
  min_rvol?: number;
}

export function useIntradayMovers(
  filters: IntradayMoversFilters = {},
  autoRefresh = true
) {
  return useQuery({
    queryKey: ["intraday-movers", filters],
    queryFn: () =>
      apiFetch<IntradayResult[]>(
        "/intraday-screener",
        filters as Record<string, number>
      ),
    refetchInterval: autoRefresh ? SCAN_REFRESH_MS : false,
  });
}
