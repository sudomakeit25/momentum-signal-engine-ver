"use client";

import { TrendingUp } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useSectorFlow } from "@/hooks/use-analytics";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function SectorFlowPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useSectorFlow();
  const sectors = (data || []) as Record<string, unknown>[];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <TrendingUp className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Sector Flow</h1>
        <span className="text-xs text-zinc-500">Dark pool + options + momentum by sector</span>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
        Aggregates dark pool accumulation, options flow sentiment, and momentum signals by sector to detect rotation. Inflow = money moving in. Outflow = money moving out.
      </div>

      {isError ? (
        <div className="rounded-lg border border-red-800/30 bg-red-900/10 p-8 text-center">
          <p className="text-sm text-zinc-300">Failed to load data.</p>
          <button onClick={() => queryClient.invalidateQueries({ queryKey: ["sector-flow"] })} className="mt-3 text-xs text-cyan-400 hover:underline">Try again</button>
        </div>
      ) : isLoading ? (
        <div className="space-y-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-20 w-full bg-zinc-800" />)}</div>
      ) : sectors.length > 0 ? (
        <div className="space-y-2">
          {sectors.map((s, i) => {
            const dir = String(s.flow_direction);
            const strength = Number(s.flow_strength);
            return (
              <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-bold text-zinc-200">{String(s.sector)}</span>
                      <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium",
                        dir === "inflow" ? "bg-emerald-400/10 text-emerald-400" : dir === "outflow" ? "bg-red-400/10 text-red-400" : "bg-zinc-400/10 text-zinc-400"
                      )}>
                        {dir.toUpperCase()}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-zinc-500">{String(s.symbols)} stocks</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-20 rounded-full bg-zinc-800">
                      <div className={cn("h-full rounded-full", dir === "inflow" ? "bg-emerald-400" : dir === "outflow" ? "bg-red-400" : "bg-zinc-600")} style={{ width: `${Math.min(strength * 100, 100)}%` }} />
                    </div>
                    <span className="min-w-[2.5rem] text-right font-mono text-xs text-zinc-400">{(strength * 100).toFixed(0)}%</span>
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-4 gap-4 text-xs">
                  <div><span className="text-zinc-500">DP Accum: </span><span className="text-emerald-400">{String(s.dp_accumulating)}</span></div>
                  <div><span className="text-zinc-500">DP Dist: </span><span className="text-red-400">{String(s.dp_distributing)}</span></div>
                  <div><span className="text-zinc-500">Opt Bull: </span><span className="text-emerald-400">{String(s.of_bullish)}</span></div>
                  <div><span className="text-zinc-500">Momentum: </span><span className="text-cyan-400">{String(s.momentum_count)}</span></div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          No sector data. Visit Dark Pool, Options Flow, and Scanner pages first to populate the cache.
        </div>
      )}
    </div>
  );
}
