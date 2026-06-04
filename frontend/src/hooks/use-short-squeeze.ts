"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export type SqueezeCandidate = {
  symbol: string;
  price: number;
  days_to_cover: number;
  shares_short: number;
  si_change_pct: number;
  price_change_5d: number;
  recent_short_vol_pct: number;
  settlement_date: string;
  squeeze_score: number;
};

export function useShortSqueeze() {
  return useQuery({
    // /signals/short-squeeze returns a raw array of candidates.
    queryKey: ["short-squeeze"],
    queryFn: () => apiFetch<SqueezeCandidate[]>("/signals/short-squeeze"),
    // Short interest settles bi-monthly and price legs update daily;
    // the endpoint is server-cached, so a 10-min refetch is plenty.
    refetchInterval: 10 * 60 * 1000,
  });
}
