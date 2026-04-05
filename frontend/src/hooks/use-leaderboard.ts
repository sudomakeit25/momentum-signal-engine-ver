"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface LeaderboardStats {
  total_tracked: number;
  resolved: number;
  pending: number;
  stats: {
    win_rate: number;
    total_wins: number;
    total_losses: number;
    periods: Record<string, { total: number; wins: number; win_rate: number }>;
  };
  by_setup: Record<string, { total: number; wins: number; win_rate: number }>;
  recent: Array<{
    symbol: string;
    action: string;
    setup_type: string;
    entry: number;
    target: number;
    stop_loss: number;
    confidence: number;
    recorded_at: string;
    outcome: string | null;
    exit_price: number | null;
    resolved_at: string | null;
  }>;
}

export function useLeaderboard() {
  return useQuery({
    queryKey: ["leaderboard"],
    queryFn: () => apiFetch<LeaderboardStats>("/leaderboard"),
    refetchInterval: 2 * 60_000,
  });
}
