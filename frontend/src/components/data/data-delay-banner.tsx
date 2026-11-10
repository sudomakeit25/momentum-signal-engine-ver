"use client";

import { Clock } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

interface Freshness {
  session_active: boolean;
  delay_minutes: number | null;
  delayed: boolean;
  note: string;
}

export function useDataFreshness() {
  return useQuery({
    queryKey: ["data-freshness"],
    queryFn: () => apiFetch<Freshness>("/data/freshness"),
    refetchInterval: 5 * 60_000,
  });
}

/** Shown on every page whose numbers come from intraday bars. Renders
 *  nothing when the data is current or the market is closed. */
export function DataDelayBanner() {
  const { data } = useDataFreshness();
  if (!data?.delayed) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400">
      <Clock className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{data.note}</span>
    </div>
  );
}
