"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { OptionsFlowResult } from "@/types/api";

export function useOptionsFlowScan(top = 20) {
  return useQuery({
    queryKey: ["options-flow-scan", top],
    queryFn: () =>
      apiFetch<OptionsFlowResult[]>("/options-flow/scan", { top }),
    refetchInterval: 5 * 60_000,
  });
}

export function useOptionsFlow(symbol: string) {
  return useQuery({
    queryKey: ["options-flow", symbol],
    queryFn: () =>
      apiFetch<OptionsFlowResult>(`/options-flow/${symbol}`),
    enabled: !!symbol,
  });
}
