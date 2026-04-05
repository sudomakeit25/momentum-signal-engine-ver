"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface SmartMoneySignal {
  source: string;
  sentiment: string;
  strength: number;
  detail: string;
}

export interface SmartMoneyResult {
  symbol: string;
  convergence_score: number;
  direction: string;
  signal_count: number;
  signals: SmartMoneySignal[];
  alert_reasons: string[];
}

export function useSmartMoney() {
  return useQuery({
    queryKey: ["smart-money"],
    queryFn: () =>
      apiFetch<SmartMoneyResult[]>("/smart-money/convergence"),
    refetchInterval: 5 * 60_000,
  });
}
