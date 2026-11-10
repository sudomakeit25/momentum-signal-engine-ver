"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

interface PriceStats {
  price: number;
  chg_5d: number;
  low_3m: number;
  high_3m: number;
  range_pos: number;
  avg_volume: number;
  last_day_pct: number;
  last_day_rvol: number;
}

export interface UpcomingCatalyst extends PriceStats {
  symbol: string;
  name: string;
  earnings_date: string;
  session: string;
  days_until: number;
  market_cap: number | null;
  days_to_cover: number;
  shares_short: number;
  si_change_pct: number;
  settlement_date: string;
  early_move: boolean;
  score: number;
}

export interface ReactingCatalyst extends PriceStats {
  symbol: string;
  name: string;
  earnings_date: string;
  session: string;
  market_cap: number | null;
  eps: number | null;
  eps_forecast: number | null;
  surprise_pct: number | null;
  days_to_cover: number;
  si_change_pct: number;
  reaction_date: string;
  reaction_pct: number;
  reaction_rvol: number;
  since_reaction_pct: number;
}

export interface CatalystWatch {
  upcoming: UpcomingCatalyst[];
  reacting: ReactingCatalyst[];
  data_ok: boolean;
  notes: string[];
  as_of: string;
  short_interest_date: string;
  calendar_symbols: { upcoming: number; reported: number };
}

export function useCatalystWatch() {
  return useQuery({
    queryKey: ["catalyst-watch"],
    queryFn: () => apiFetch<CatalystWatch>("/scanner/catalyst-watch"),
    // The server caches a good scan for 30 minutes; a failed one is retried sooner.
    staleTime: (query) => (query.state.data?.data_ok === false ? 60 * 1000 : 15 * 60 * 1000),
  });
}
