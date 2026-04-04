"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart2, TrendingUp, TrendingDown, Activity } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Signal, ScanResult } from "@/types/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function PerformancePage() {
  const { data: signals, isLoading: sigLoading } = useQuery({
    queryKey: ["signals", 50],
    queryFn: () => apiFetch<Signal[]>("/signals", { top: 50 }),
  });

  const { data: scanResults, isLoading: scanLoading } = useQuery({
    queryKey: ["scan", 50],
    queryFn: () => apiFetch<ScanResult[]>("/scan", { top: 50 }),
  });

  const { data: breadth } = useQuery({
    queryKey: ["breadth"],
    queryFn: () =>
      apiFetch<{
        total: number;
        bullish: number;
        bearish: number;
        neutral: number;
        above_ema21: number;
        bullish_pct: number;
        above_ema21_pct: number;
      }>("/breadth"),
  });

  const isLoading = sigLoading || scanLoading;

  // Compute dashboard metrics
  const buySignals = signals?.filter((s) => s.action === "BUY") ?? [];
  const sellSignals = signals?.filter((s) => s.action === "SELL") ?? [];
  const avgConfidence = signals?.length
    ? signals.reduce((sum, s) => sum + s.confidence, 0) / signals.length
    : 0;
  const avgScore = scanResults?.length
    ? scanResults.reduce((sum, r) => sum + r.score, 0) / scanResults.length
    : 0;
  const topScorers = [...(scanResults ?? [])].sort((a, b) => b.score - a.score).slice(0, 10);
  const topGainers = [...(scanResults ?? [])].sort((a, b) => b.change_pct - a.change_pct).slice(0, 5);
  const topLosers = [...(scanResults ?? [])].sort((a, b) => a.change_pct - b.change_pct).slice(0, 5);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <BarChart2 className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Performance Dashboard</h1>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-20 bg-zinc-800" />
          ))}
        </div>
      ) : (
        <>
          {/* Overview cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Total Signals" value={signals?.length ?? 0} />
            <StatCard label="Buy Signals" value={buySignals.length} valueColor="text-emerald-400" />
            <StatCard label="Sell Signals" value={sellSignals.length} valueColor="text-red-400" />
            <StatCard label="Avg Confidence" value={`${(avgConfidence * 100).toFixed(0)}%`} />
            <StatCard label="Stocks Scanned" value={scanResults?.length ?? 0} />
            <StatCard label="Avg Score" value={avgScore.toFixed(1)} />
            <StatCard
              label="Market Bullish"
              value={`${breadth?.bullish_pct ?? 0}%`}
              valueColor={
                (breadth?.bullish_pct ?? 0) >= 60 ? "text-emerald-400" : (breadth?.bullish_pct ?? 0) <= 40 ? "text-red-400" : "text-yellow-400"
              }
            />
            <StatCard label="Above EMA21" value={`${breadth?.above_ema21_pct ?? 0}%`} />
          </div>

          {/* Signal distribution */}
          {signals && signals.length > 0 && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <h3 className="mb-3 text-sm font-semibold text-zinc-300">Signal Strength Distribution</h3>
              <div className="flex h-8 w-full overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="bg-emerald-600 transition-all flex items-center justify-center text-[10px] font-bold text-white"
                  style={{ width: `${(buySignals.length / signals.length) * 100}%` }}
                >
                  {buySignals.length > 0 && `${buySignals.length} BUY`}
                </div>
                <div
                  className="bg-red-600 transition-all flex items-center justify-center text-[10px] font-bold text-white"
                  style={{ width: `${(sellSignals.length / signals.length) * 100}%` }}
                >
                  {sellSignals.length > 0 && `${sellSignals.length} SELL`}
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {/* Top momentum */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-300">
                <Activity className="h-4 w-4 text-cyan-400" /> Top Momentum
              </h3>
              <div className="space-y-2">
                {topScorers.map((r, i) => (
                  <div key={r.symbol} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span className="w-5 text-right text-xs text-zinc-500">{i + 1}</span>
                      <span className="font-bold text-cyan-400">{r.symbol}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={cn("text-xs", r.change_pct >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {r.change_pct >= 0 ? "+" : ""}{r.change_pct}%
                      </span>
                      <span className={cn(
                        "rounded px-1.5 py-0.5 text-xs font-mono font-bold",
                        r.score >= 70 ? "bg-emerald-500/20 text-emerald-400" : r.score >= 40 ? "bg-yellow-500/20 text-yellow-400" : "bg-red-500/20 text-red-400"
                      )}>
                        {r.score}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Top gainers */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-300">
                <TrendingUp className="h-4 w-4 text-emerald-400" /> Top Gainers
              </h3>
              <div className="space-y-2">
                {topGainers.map((r) => (
                  <div key={r.symbol} className="flex items-center justify-between text-sm">
                    <span className="font-bold text-cyan-400">{r.symbol}</span>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs">${r.price.toFixed(2)}</span>
                      <span className="text-xs font-bold text-emerald-400">+{r.change_pct}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Top losers */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-300">
                <TrendingDown className="h-4 w-4 text-red-400" /> Top Losers
              </h3>
              <div className="space-y-2">
                {topLosers.map((r) => (
                  <div key={r.symbol} className="flex items-center justify-between text-sm">
                    <span className="font-bold text-cyan-400">{r.symbol}</span>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs">${r.price.toFixed(2)}</span>
                      <span className="text-xs font-bold text-red-400">{r.change_pct}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Active signals detail */}
          {signals && signals.length > 0 && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <h3 className="mb-3 text-sm font-semibold text-zinc-300">Highest Confidence Signals</h3>
              <div className="space-y-2">
                {signals.slice(0, 10).map((s, i) => (
                  <div key={`${s.symbol}-${s.action}-${i}`} className="flex items-center justify-between rounded bg-zinc-800/50 px-3 py-2 text-sm">
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-bold",
                          s.action === "BUY" ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"
                        )}
                      >
                        {s.action}
                      </span>
                      <span className="font-bold text-cyan-400">{s.symbol}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="text-zinc-400">{s.setup_type.replace(/_/g, " ")}</span>
                      <span className="font-mono font-bold">{(s.confidence * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string | number;
  valueColor?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className={cn("text-xl font-bold font-mono", valueColor)}>{value}</p>
    </div>
  );
}
