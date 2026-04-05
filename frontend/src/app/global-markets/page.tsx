"use client";

import { Globe } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function GlobalMarketsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["global"], queryFn: () => apiFetch<{ markets: Record<string, unknown>[] }>("/market/global"), refetchInterval: 60_000 });
  const { data: yc } = useQuery({ queryKey: ["yield-curve"], queryFn: () => apiFetch<Record<string, unknown>>("/market/yield-curve") });

  const markets = data?.markets || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Globe className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Global Markets</h1>
      </div>

      {isLoading ? <div className="grid grid-cols-3 gap-2">{Array.from({ length: 12 }).map((_, i) => <Skeleton key={i} className="h-20 bg-zinc-800" />)}</div> : (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {markets.map((m, i) => (
            <div key={i} className={cn("rounded-lg border p-3", Number(m.change_1d) >= 0 ? "border-emerald-800/20 bg-emerald-900/5" : "border-red-800/20 bg-red-900/5")}>
              <p className="text-xs text-zinc-500">{String(m.label)}</p>
              <p className="text-lg font-bold text-zinc-200">${String(m.price)}</p>
              <div className="flex gap-2 text-xs">
                <span className={cn("font-mono", Number(m.change_1d) >= 0 ? "text-emerald-400" : "text-red-400")}>{Number(m.change_1d) >= 0 ? "+" : ""}{String(m.change_1d)}%</span>
                <span className={cn("font-mono", Number(m.change_5d) >= 0 ? "text-emerald-400/60" : "text-red-400/60")}>{Number(m.change_5d) >= 0 ? "+" : ""}{String(m.change_5d)}% 5d</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Yield Curve */}
      {yc && !yc.error && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-zinc-300">Treasury Yield Curve</h2>
            {Boolean(yc.inverted) && <span className="rounded-full bg-red-400/10 px-2 py-0.5 text-xs text-red-400">INVERTED</span>}
          </div>
          <div className="flex items-end gap-2 h-32">
            {Object.entries((yc.maturities || {}) as Record<string, number>).map(([mat, rate]) => {
              const height = Math.max((rate / 6) * 100, 5);
              return (
                <div key={mat} className="flex-1 flex flex-col items-center justify-end">
                  <span className="text-[10px] text-zinc-400 font-mono mb-1">{rate}%</span>
                  <div className={cn("w-full rounded-t", Boolean(yc.inverted) ? "bg-red-400/60" : "bg-cyan-400/60")} style={{ height: `${height}%` }} />
                  <span className="text-[10px] text-zinc-600 mt-1">{mat}</span>
                </div>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-zinc-500 text-center">2y/10y Spread: {String(yc.spread_2_10)}% {Boolean(yc.inverted) ? "(Recession warning)" : ""}</p>
        </div>
      )}
    </div>
  );
}
