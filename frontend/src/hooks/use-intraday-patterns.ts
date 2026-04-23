"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export type IntradayPattern = {
  symbol: string;
  pattern_type:
    | "v_reversal"
    | "inverted_v"
    | "breakdown"
    | "breakout"
    | string;
  action: "BUY" | "SELL" | string;
  trigger_price: number;
  extreme_price: number;
  move_pct: number;
  recovery_pct: number;
  volume_confirmed: boolean;
  detected_at: string;
};

type Response = { patterns: IntradayPattern[] };

export function useIntradayPatterns() {
  return useQuery({
    queryKey: ["intraday-patterns"],
    queryFn: () => apiFetch<Response>("/scanner/intraday-patterns"),
    // Backend re-runs every 5 minutes; refetch every 60s so the UI
    // catches the new batch within at most one minute.
    refetchInterval: 60_000,
  });
}
