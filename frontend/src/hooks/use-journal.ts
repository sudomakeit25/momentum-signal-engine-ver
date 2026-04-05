"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

export interface Trade {
  id: string;
  symbol: string;
  side: string;
  shares: number;
  entry_price: number;
  exit_price: number | null;
  stop_loss: number | null;
  target: number | null;
  status: "open" | "closed";
  setup_type: string;
  notes: string;
  entry_date: string;
  exit_date: string | null;
  pnl: number | null;
  r_multiple: number | null;
  created_at: string;
}

export interface JournalStats {
  total_trades: number;
  closed_trades: number;
  open_trades: number;
  win_rate: number;
  avg_pnl: number;
  total_pnl: number;
  avg_r_multiple: number;
  expectancy: number;
  largest_win: number;
  largest_loss: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  by_setup: Record<string, { trades: number; wins: number; win_rate: number; pnl: number }>;
}

export function useTrades() {
  return useQuery({
    queryKey: ["journal-trades"],
    queryFn: () => apiFetch<Trade[]>("/journal/trades"),
  });
}

export function useJournalStats() {
  return useQuery({
    queryKey: ["journal-stats"],
    queryFn: () => apiFetch<JournalStats>("/journal/stats"),
  });
}

export function useAddTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: Record<string, string | number>) =>
      apiPost("/journal/trades", params),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal-trades"] });
      qc.invalidateQueries({ queryKey: ["journal-stats"] });
    },
  });
}

export function useCloseTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ tradeId, exitPrice }: { tradeId: string; exitPrice: number }) =>
      apiPost(`/journal/trades/${tradeId}/close`, { exit_price: exitPrice }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal-trades"] });
      qc.invalidateQueries({ queryKey: ["journal-stats"] });
    },
  });
}

export function useImportAlpaca() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (days: number = 30) =>
      apiPost("/journal/import-alpaca", { days }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal-trades"] });
      qc.invalidateQueries({ queryKey: ["journal-stats"] });
    },
  });
}

export function useAlertHistory(limit = 100, enrich = true) {
  return useQuery({
    queryKey: ["alert-history", limit, enrich],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/alerts/history", { limit, enrich: enrich ? "true" : "false" }),
  });
}

export function useSignalBacktest(symbol: string, days = 200, lookforward = 10) {
  return useQuery({
    queryKey: ["signal-backtest", symbol, days, lookforward],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/backtest/signals/${symbol}`, { days, lookforward }),
    enabled: !!symbol,
  });
}
