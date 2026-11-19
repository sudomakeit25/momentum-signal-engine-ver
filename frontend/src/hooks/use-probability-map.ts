"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
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

export interface LiveWindow {
  sessions: number;
  days: number;
  cells: number;
  skill: number | null;
}

// Totals from forecasts saved after each close and scored once their windows finished.
export interface LiveSummary {
  days: Record<string, number>;
  cells: number;
  skill: number | null;
  skill_10: number | null;
  verdict: string | null;
  by_window: LiveWindow[];
  bins: MapBin[];
  next: {
    days: number;
    open_days: number;
    happened: number;
    skill: number | null;
    verdict: string | null;
    open_skill: number | null;
    open_verdict: string | null;
  };
  min_days: number;
}

// One stock's live record; days is null when the stock is not in the daily record.
export type LiveRecord =
  | ({ since: string; last_saved: string } & LiveSummary)
  | { since: string; last_saved: string; days: null };

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
  live: LiveRecord | null;
}

// retry: the server was busy or a download failed; worth asking again shortly.
export type ProbabilityMap =
  | ProbabilityMapOk
  | { symbol: string; data_ok: false; note: string; retry?: boolean };

export function useProbabilityMap(symbol: string) {
  return useQuery({
    queryKey: ["probability-map", symbol],
    queryFn: () => apiFetch<ProbabilityMap>(`/probability-map/${encodeURIComponent(symbol)}`),
    enabled: !!symbol,
    // The server caches a good answer for 10 minutes; a failed one is retried sooner.
    staleTime: (query) => (query.state.data?.data_ok === false ? 30 * 1000 : 10 * 60 * 1000),
    // A busy or failed build is temporary: ask again every 5 seconds for the
    // first minute, then every 30 seconds for about five more, then stop.
    refetchInterval: (query) => {
      const d = query.state.data;
      if (!d || d.data_ok || !d.retry || query.state.dataUpdateCount > MAX_TRIES) return false;
      return query.state.dataUpdateCount <= 12 ? 5000 : 30000;
    },
  });
}

export const MAX_TRIES = 22;

// True once the panel has stopped asking again for a map that kept failing.
export function useProbabilityMapGaveUp(symbol: string): boolean {
  const tries = useQueryClient().getQueryState(["probability-map", symbol])?.dataUpdateCount ?? 0;
  return tries > MAX_TRIES;
}
