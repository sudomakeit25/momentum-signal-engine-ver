"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { SCAN_REFRESH_MS } from "@/lib/constants";

export interface BreadthData {
  total: number;
  bullish: number;
  bearish: number;
  neutral: number;
  above_ema21: number;
  bullish_pct: number;
  above_ema21_pct: number;
}

export function useBreadth() {
  return useQuery({
    queryKey: ["breadth"],
    queryFn: () => apiFetch<BreadthData>("/breadth"),
    refetchInterval: SCAN_REFRESH_MS,
  });
}
