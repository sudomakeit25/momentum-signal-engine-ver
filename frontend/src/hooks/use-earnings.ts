"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { EarningsConviction, EarningsEvent, InsiderTrade } from "@/types/api";

export function useEarningsUpcoming(daysAhead = 14) {
  return useQuery({
    queryKey: ["earnings-upcoming", daysAhead],
    queryFn: () =>
      apiFetch<EarningsEvent[]>("/earnings/upcoming", { days_ahead: daysAhead }),
    refetchInterval: 10 * 60_000,
  });
}

export function useEarningsWhisper(daysAhead = 14, minConviction = 0) {
  return useQuery({
    queryKey: ["earnings-whisper", daysAhead, minConviction],
    queryFn: () =>
      apiFetch<EarningsConviction[]>("/earnings/whisper", {
        days_ahead: daysAhead,
        min_conviction: minConviction,
      }),
    refetchInterval: 10 * 60_000,
  });
}

export function useEarningsConviction(symbol: string) {
  return useQuery({
    queryKey: ["earnings-conviction", symbol],
    queryFn: () =>
      apiFetch<EarningsConviction>(`/earnings/conviction/${symbol}`),
    enabled: !!symbol,
  });
}

export function useInsiderTrades(symbol: string, limit = 20) {
  return useQuery({
    queryKey: ["insider-trades", symbol, limit],
    queryFn: () =>
      apiFetch<InsiderTrade[]>(`/insider/${symbol}`, { limit }),
    enabled: !!symbol,
  });
}
