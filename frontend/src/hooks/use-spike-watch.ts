"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface SpikeEvent {
  symbol: string;
  kind: string;
  direction: "up" | "down";
  price: number;
  time: string;
  detail: string;
  headline?: string;
  multiple?: number;
  level?: number;
}

export interface StretchedRow {
  symbol: string;
  price: number;
  move_5d_pct: number;
  direction: "up" | "down";
  headline?: string;
}

export interface SympathyRow {
  group: string;
  leader: string;
  leader_change_pct: number;
  leader_rvol: number;
  laggards: { symbol: string; change_pct: number }[];
  headline?: string;
}

export interface SpikeWatch {
  events: SpikeEvent[];
  stretched: StretchedRow[];
  sympathy: SympathyRow[];
  data_ok: boolean;
  notes: string[];
  market_open: boolean;
  as_of: string;
}

export function useSpikeWatch() {
  return useQuery({
    queryKey: ["spike-watch"],
    queryFn: () => apiFetch<SpikeWatch>("/scanner/spike-watch"),
    refetchInterval: 60_000,
  });
}

export interface HorizonStat {
  n: number;
  win_pct: number | null;
  avg_pct: number | null;
}

export interface ScorecardRow {
  kind: string;
  direction: "up" | "down";
  alerts: number;
  m15: HorizonStat;
  h1: HorizonStat;
  eod: HorizonStat;
  d1: HorizonStat;
  d5: HorizonStat;
  first_touch: { n: number; target: number; stop: number; neither: number } | null;
}

export interface ScorecardRecord {
  id: string;
  ts: string;
  date: string;
  symbol: string;
  kind: string;
  direction: "up" | "down";
  price: number;
  stop: number | null;
  target: number | null;
  outcome: Partial<Record<"m15" | "h1" | "eod" | "d1" | "d5", number>> & {
    first_touch?: string;
  };
  final: boolean;
}

export interface Scorecard {
  days: number;
  total_alerts: number;
  first_date: string;
  summary: ScorecardRow[];
  recent: ScorecardRecord[];
  horizons: Record<string, string>;
}

export function useScorecard(days: number) {
  return useQuery({
    queryKey: ["scorecard", days],
    queryFn: () => apiFetch<Scorecard>("/scorecard", { days }),
    staleTime: 5 * 60 * 1000,
  });
}
