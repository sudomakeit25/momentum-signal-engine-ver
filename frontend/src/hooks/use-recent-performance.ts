"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface PerformanceRow {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  change_pct: number | null;
  volume: number | null;
  rvol: number | null;
  cum_pct: number;
  big: boolean;
}

export interface PerformanceHeadline {
  headline: string;
  source: string;
  time: string;
  url: string;
  specific: boolean;
}

export interface BigDay {
  date: string;
  change_pct: number;
  rvol: number | null;
  // null = the news feed could not be read; [] = no headlines that day
  headlines: PerformanceHeadline[] | null;
}

export interface RecentPerformance {
  symbol: string;
  data_ok: boolean;
  note: string | null;
  sessions: number;
  sessions_requested: number;
  base_date: string;
  base_close: number;
  last_date: string;
  last_close: number;
  change_pct: number;
  high: number;
  high_date: string;
  low: number;
  low_date: string;
  range_pos: number | null;
  up_days: number;
  down_days: number;
  best_day: { date: string; change_pct: number } | null;
  worst_day: { date: string; change_pct: number } | null;
  avg_abs_move: number | null;
  typical_move: number | null;
  rows: PerformanceRow[];
  in_progress: boolean;
  peer_group: string | null;
  compared: { symbol: string; change_pct: number; is_market: boolean }[];
  big_days: BigDay[];
  big_day_rule: string | null;
}

export function useRecentPerformance(symbol: string, sessions: number) {
  return useQuery({
    queryKey: ["recent-performance", symbol, sessions],
    queryFn: () =>
      apiFetch<RecentPerformance>(`/recent-performance/${encodeURIComponent(symbol)}`, { sessions }),
    enabled: !!symbol,
    // The server caches a good answer for 5 minutes; a failed one is retried sooner.
    staleTime: (query) => (query.state.data?.data_ok === false ? 30 * 1000 : 5 * 60 * 1000),
  });
}
