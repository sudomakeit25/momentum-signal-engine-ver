"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost, apiPostJson } from "@/lib/api";
import { getAuthToken } from "@/hooks/use-auth";

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
  store_ok: boolean;
  resume_hint: string;
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
    // Pausing is open (it can only make the bot safer). Resuming needs a
    // logged-in user, so it sends the session token.
    mutationFn: async (pause: boolean) => {
      if (pause) return apiPost<AutoTraderStatus>("/trading/auto/pause");
      const token = getAuthToken();
      if (!token) throw new Error("Log in to resume the auto-trader");
      return apiPostJson<AutoTraderStatus>(
        "/trading/auto/resume",
        {},
        { Authorization: `Bearer ${token}` }
      );
    },
    onSuccess: (data) => queryClient.setQueryData(["auto-trader"], data),
  });
}
