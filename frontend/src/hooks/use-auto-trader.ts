"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

export interface AutoTrade {
  time: string;
  symbol: string;
  setup: string;
  side: string;
  qty: number;
  signal_entry: number;
  quote_at_order: number;
  stop: number;
  target: number;
  risk_usd: number;
  order_id: string;
  status: string;
}

export interface AutoSkip {
  time: string;
  symbol: string;
  setup: string;
  action: string;
  reason: string;
}

export interface AutoTraderStatus {
  mode: string;
  enabled: boolean;
  paused: boolean;
  paper: boolean;
  config: {
    risk_per_trade_usd: number;
    max_position_usd: number;
    max_trades_per_day: number;
    max_open_positions: number;
    daily_loss_limit_usd: number;
    allow_shorts: boolean;
    last_entry: string;
    flatten_at: string;
  };
  date: string;
  halted: string;
  flattened: boolean;
  trades: AutoTrade[];
  skips: AutoSkip[];
}

export function useAutoTrader() {
  return useQuery({
    queryKey: ["auto-trader"],
    queryFn: () => apiFetch<AutoTraderStatus>("/trading/auto/status"),
    refetchInterval: 30_000,
  });
}

export function useAutoTraderPause() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pause: boolean) =>
      apiPost<AutoTraderStatus>(
        pause ? "/trading/auto/pause" : "/trading/auto/resume"
      ),
    onSuccess: (data) => queryClient.setQueryData(["auto-trader"], data),
  });
}
