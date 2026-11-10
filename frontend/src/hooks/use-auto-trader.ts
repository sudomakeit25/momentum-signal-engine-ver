"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost, apiPostJson } from "@/lib/api";

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
  notices: { date: string; symbol: string; text: string }[];
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
    // Pausing is open (it can only make the bot safer). Resuming needs the
    // server-side resume key, typed in by the owner and never stored.
    mutationFn: async (action: { pause: true } | { pause: false; key: string }) => {
      if (action.pause) return apiPost<AutoTraderStatus>("/trading/auto/pause");
      if (!action.key) throw new Error("Enter the resume key");
      try {
        return await apiPostJson<AutoTraderStatus>(
          "/trading/auto/resume",
          {},
          { "X-Resume-Key": action.key }
        );
      } catch {
        throw new Error("Resume refused: wrong key, or resume is not set up on the server");
      }
    },
    onSuccess: (data) => queryClient.setQueryData(["auto-trader"], data),
  });
}
