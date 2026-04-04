"use client";

import { useQuery } from "@tanstack/react-query";
import { TrendingUp } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface SectorData {
  sector: string;
  avg_change_pct: number;
  avg_rs: number;
  avg_score: number;
  count: number;
  top_stock: string;
}

function useSectors() {
  return useQuery({
    queryKey: ["sectors"],
    queryFn: () => apiFetch<SectorData[]>("/sectors"),
    refetchInterval: 60_000,
  });
}

export default function SectorsPage() {
  const { data, isLoading } = useSectors();

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <TrendingUp className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Sector Rotation</h1>
      </div>

      {isLoading && !data ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-28 bg-zinc-800" />
          ))}
        </div>
      ) : data && data.length > 0 ? (
        <>
          {/* Bar chart */}
          <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <h2 className="mb-3 text-sm font-medium text-zinc-400">Change % by Sector (Today)</h2>
            {data.map((s) => {
              const maxAbs = Math.max(...data.map((d) => Math.abs(d.avg_change_pct)), 1);
              const width = Math.abs(s.avg_change_pct) / maxAbs * 100;
              return (
                <div key={s.sector} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 text-right text-xs font-medium text-zinc-300">
                    {s.sector}
                  </span>
                  <div className="relative flex h-6 flex-1 items-center">
                    <div
                      className={cn(
                        "h-full rounded-sm transition-all",
                        s.avg_change_pct >= 0 ? "bg-emerald-500/70" : "bg-red-500/70"
                      )}
                      style={{ width: `${Math.max(width, 2)}%` }}
                    />
                    <span
                      className={cn(
                        "ml-2 text-xs font-mono font-bold",
                        s.avg_change_pct >= 0 ? "text-emerald-400" : "text-red-400"
                      )}
                    >
                      {s.avg_change_pct >= 0 ? "+" : ""}{s.avg_change_pct.toFixed(2)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.map((s, i) => (
              <div
                key={s.sector}
                className={cn(
                  "rounded-lg border p-4",
                  i === 0
                    ? "border-emerald-700 bg-emerald-950/30"
                    : i === data.length - 1
                    ? "border-red-700 bg-red-950/30"
                    : "border-zinc-800 bg-zinc-900/50"
                )}
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-zinc-100">{s.sector}</h3>
                  <span className="text-xs text-zinc-500">#{i + 1}</span>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                  <div>
                    <p className={cn("text-lg font-bold font-mono", s.avg_change_pct >= 0 ? "text-emerald-400" : "text-red-400")}>
                      {s.avg_change_pct >= 0 ? "+" : ""}{s.avg_change_pct.toFixed(2)}%
                    </p>
                    <p className="text-[10px] text-zinc-500">Avg Change</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold font-mono text-zinc-200">{s.avg_rs.toFixed(2)}</p>
                    <p className="text-[10px] text-zinc-500">Avg RS</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold font-mono text-zinc-200">{s.avg_score.toFixed(0)}</p>
                    <p className="text-[10px] text-zinc-500">Avg Score</p>
                  </div>
                </div>
                <p className="mt-2 text-xs text-zinc-500">
                  {s.count} stocks | Leader: <span className="text-cyan-400">{s.top_stock}</span>
                </p>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          No sector data available.
        </div>
      )}
    </div>
  );
}
