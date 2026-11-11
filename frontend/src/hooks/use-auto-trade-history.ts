"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface HistoryTrade {
  date: string;
  symbol: string;
  setup: string;
  side: string;
  qty: number;
  entry_price: number | null;
  entry_time: number | null;
  stop: number | null;
  target: number | null;
  exit_price: number | null;
  exit_qty: number;
  exit_reason: string;
  exit_reasons: Record<string, number>;
  exit_time: number | null;
  outcome: "closed" | "open" | "closed outside the bot";
  open_qty: number;
  pnl: number | null;
  r_multiple: number | null;
  client_order_id: string;
}

export interface HistoryGroup {
  date?: string;
  setup?: string;
  trades: number;
  closed: number;
  open: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  pnl: number;
  avg_r: number | null;
}

export interface HistoryTotals {
  trades: number;
  closed: number;
  open: number;
  closed_outside: number;
  not_filled: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  pnl: number;
  avg_r: number | null;
  best: { symbol: string; date: string; pnl: number } | null;
  worst: { symbol: string; date: string; pnl: number } | null;
}

export interface AutoTradeHistory {
  data_ok: boolean;
  days: number;
  note: string | null;
  since?: string;
  as_of?: string;
  totals?: HistoryTotals;
  by_day?: HistoryGroup[];
  by_setup?: HistoryGroup[];
  trades?: HistoryTrade[];
}

export function useAutoTradeHistory(days: number) {
  return useQuery({
    queryKey: ["auto-trade-history", days],
    queryFn: () => apiFetch<AutoTradeHistory>("/trading/auto/history", { days }),
    refetchInterval: 60 * 1000,
  });
}
