"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { BacktestResult } from "@/types/api";

interface BacktestParams {
  symbol: string;
  days: number;
  capital: number;
  risk_pct: number;
}

export function useBacktest(params: BacktestParams, enabled = false) {
  return useQuery({
    queryKey: ["backtest", params],
    queryFn: () =>
      apiFetch<BacktestResult>("/backtest", {
        symbol: params.symbol,
        days: params.days,
        capital: params.capital,
        risk_pct: params.risk_pct,
      }),
    enabled,
  });
}
