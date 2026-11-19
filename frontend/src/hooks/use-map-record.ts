"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { LiveSummary } from "@/hooks/use-probability-map";

export interface MapRecordReport {
  ok: boolean;
  note?: string;
  since?: string | null;
  last_saved?: string;
  sessions_saved?: number;
  stocks?: number;
  stocks_scored?: number;
  updated?: string;
  waiting?: string[];
  pooled?: LiveSummary;
  focus?: (LiveSummary & { symbol: string })[];
}

export function useMapRecord() {
  return useQuery({
    queryKey: ["probability-map-record"],
    queryFn: () => apiFetch<MapRecordReport>("/probability-map-record"),
    staleTime: 5 * 60 * 1000,
  });
}
