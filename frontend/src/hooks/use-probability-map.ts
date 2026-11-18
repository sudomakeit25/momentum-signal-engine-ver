"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface MapRow {
  level_pct: number;
  price: number;
  // one per horizon; null if it could not be computed
  odds: (number | null)[];
  usual: (number | null)[];
}

export interface MapBin {
  lo: number;
  hi: number;
  n: number;
  said: number;
  happened: number;
}

export interface MapCheck {
  sessions: number;
  from?: string;
  to?: string;
  skill?: number | null;
  skill_10?: number | null;
  verdict?: string | null;
  bins?: MapBin[];
  big_day?: {
    sessions: number;
    happened: number;
    from: string;
    to: string;
    skill: number | null;
    verdict: string | null;
    open_skill: number | null;
    open_verdict: string | null;
  };
}

export interface ProbabilityMapOk {
  symbol: string;
  data_ok: true;
  note: null;
  as_of: string;
  last_close: number;
  history_sessions: number;
  history_from: string;
  vol_pct: number;
  vol_usual_pct: number;
  levels: number[];
  horizons: number[];
  rows: MapRow[];
  big_day: {
    level_pct: number;
    up: number;
    down: number;
    usual_up: number;
    usual_down: number;
    cases: number;
  };
  today: {
    date: string | null;
    open: number;
    gap_pct: number;
    up: number;
    down: number;
    cases: number;
  } | null;
  calibration: MapCheck | null;
  earnings: { known: boolean; date: string | null; sessions_away: number | null };
  in_progress: boolean;
}

export type ProbabilityMap = ProbabilityMapOk | { symbol: string; data_ok: false; note: string };

export function useProbabilityMap(symbol: string) {
  return useQuery({
    queryKey: ["probability-map", symbol],
    queryFn: () => apiFetch<ProbabilityMap>(`/probability-map/${encodeURIComponent(symbol)}`),
    enabled: !!symbol,
    // The server caches a good answer for 10 minutes; a failed one is retried sooner.
    staleTime: (query) => (query.state.data?.data_ok === false ? 30 * 1000 : 10 * 60 * 1000),
  });
}
