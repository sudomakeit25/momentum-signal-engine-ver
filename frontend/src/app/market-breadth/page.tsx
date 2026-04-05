"use client";

import { BarChart2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function Stat({ label, value, color, sub }: { label: string; value: string | number; color?: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
      <p className={cn("text-xl font-bold", color || "text-zinc-200")}>{value}</p>
      <p className="text-[10px] text-zinc-500">{label}</p>
      {sub && <p className="text-[10px] text-zinc-600">{sub}</p>}
    </div>
  );
}

function BarMeter({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs"><span className="text-zinc-400">{label}</span><span className={cn("font-mono", color)}>{pct}%</span></div>
      <div className="h-2 rounded-full bg-zinc-800"><div className={cn("h-full rounded-full", color.replace("text-", "bg-"))} style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

export default function MarketBreadthPage() {
  const { data: breadth, isLoading } = useQuery({ queryKey: ["breadth"], queryFn: () => apiFetch<Record<string, unknown>>("/market/breadth"), refetchInterval: 5 * 60_000 });
  const { data: econ } = useQuery({ queryKey: ["econ-cal"], queryFn: () => apiFetch<Record<string, unknown>[]>("/market/economic-calendar") });
  const { data: fg } = useQuery({ queryKey: ["crypto-fg"], queryFn: () => apiFetch<Record<string, unknown>>("/market/crypto-fear-greed") });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <BarChart2 className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Market Breadth</h1>
      </div>

      {isLoading ? <div className="grid grid-cols-4 gap-3">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-20 bg-zinc-800" />)}</div> : breadth && !breadth.error ? (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Advancing" value={String(breadth.advancing)} color="text-emerald-400" />
            <Stat label="Declining" value={String(breadth.declining)} color="text-red-400" />
            <Stat label="A/D Ratio" value={String(breadth.ad_ratio)} color={Number(breadth.ad_ratio) > 1 ? "text-emerald-400" : "text-red-400"} />
            <Stat label="Signal" value={String(breadth.breadth_signal).toUpperCase()} color={breadth.breadth_signal === "bullish" ? "text-emerald-400" : breadth.breadth_signal === "bearish" ? "text-red-400" : "text-zinc-400"} />
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="52w Highs" value={String(breadth.new_52w_highs)} color="text-emerald-400" />
            <Stat label="52w Lows" value={String(breadth.new_52w_lows)} color="text-red-400" />
            <Stat label="Total Stocks" value={String(breadth.total_stocks)} />
            <Stat label="Unchanged" value={String(breadth.unchanged)} />
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
            <h2 className="text-sm font-medium text-zinc-300">% Above Moving Averages</h2>
            <BarMeter label="Above 20 SMA" pct={Number(breadth.above_20sma_pct)} color={Number(breadth.above_20sma_pct) > 50 ? "text-emerald-400" : "text-red-400"} />
            <BarMeter label="Above 50 SMA" pct={Number(breadth.above_50sma_pct)} color={Number(breadth.above_50sma_pct) > 50 ? "text-emerald-400" : "text-red-400"} />
            <BarMeter label="Above 200 SMA" pct={Number(breadth.above_200sma_pct)} color={Number(breadth.above_200sma_pct) > 50 ? "text-emerald-400" : "text-red-400"} />
          </div>
        </>
      ) : <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500">No breadth data available.</div>}

      {/* Crypto Fear & Greed */}
      {fg && !fg.error && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <h2 className="text-sm font-medium text-zinc-300 mb-2">Crypto Fear & Greed</h2>
          <div className="flex items-center gap-4">
            <div className={cn("text-3xl font-bold", Number(fg.value) > 60 ? "text-emerald-400" : Number(fg.value) < 40 ? "text-red-400" : "text-amber-400")}>{String(fg.value)}</div>
            <div className="text-xs text-zinc-400">{String(fg.classification)}</div>
          </div>
        </div>
      )}

      {/* Economic Calendar */}
      {econ && econ.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-zinc-300">Economic Calendar</h2>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-zinc-800 bg-zinc-900/50 text-zinc-400"><th className="px-3 py-2 text-left">Date</th><th className="px-3 py-2 text-left">Event</th><th className="px-3 py-2 text-right">Actual</th><th className="px-3 py-2 text-right">Est</th><th className="px-3 py-2 text-right">Prev</th></tr></thead>
              <tbody>{econ.map((e, i) => (
                <tr key={i} className="border-b border-zinc-800/30"><td className="px-3 py-1.5 text-zinc-500">{String(e.date).slice(0, 10)}</td><td className="px-3 py-1.5 text-zinc-300">{String(e.event)}</td><td className="px-3 py-1.5 text-right font-mono text-zinc-300">{e.actual != null ? String(e.actual) : "-"}</td><td className="px-3 py-1.5 text-right font-mono text-zinc-500">{e.estimate != null ? String(e.estimate) : "-"}</td><td className="px-3 py-1.5 text-right font-mono text-zinc-500">{e.previous != null ? String(e.previous) : "-"}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
