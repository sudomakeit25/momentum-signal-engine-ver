"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export type Cyclical = {
  symbol: string;
  cycles: number;
  mean_amplitude_pct: number;
  amplitude_cv: number;
  mean_period_bars: number;
  period_cv: number;
  range_position: number;
  range_low: number;
  range_high: number;
  current_price: number;
  cyclical_score: number;
  bias: "BUY" | "SELL" | "HOLD" | string;
};

type Response = { cyclicals: Cyclical[]; generated_at: number | null };

export function useCyclicals() {
  return useQuery({
    queryKey: ["cyclicals"],
    queryFn: () => apiFetch<Response>("/scanner/cyclicals"),
    // Backend refreshes hourly; one refetch every 10 min is enough.
    refetchInterval: 10 * 60 * 1000,
  });
}
