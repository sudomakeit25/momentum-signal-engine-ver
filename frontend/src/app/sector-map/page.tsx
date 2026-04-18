"use client";

import { Activity } from "lucide-react";
import { useSectorMap } from "@/hooks/use-trading";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Legend, ReferenceLine,
} from "recharts";

const SECTOR_COLORS: Record<string, string> = {
  SPY: "#000000",
  XLF: "#ef4444",
  XLE: "#c2410c",
  XLU: "#f59e0b",
  XLB: "#60a5fa",
  XLRE: "#ec4899",
  XLV: "#b91c1c",
  XLY: "#10b981",
  XLI: "#84cc16",
  XLC: "#78350f",
  XLK: "#dc2626",
  XLP: "#06b6d4",
};

type Rank = { symbol: string; label: string; return_pct: number };

export default function SectorMapPage() {
  const { data, isLoading } = useSectorMap(365);

  const series = ((data?.series as Record<string, number | string>[] | undefined) ?? []);
  const ranking = ((data?.ranking as Rank[] | undefined) ?? []);
  const sectors = Object.keys(SECTOR_COLORS);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Activity className="h-5 w-5 text-cyan-400" />
        <div>
          <h1 className="text-lg font-bold">Sector Map</h1>
          <p className="text-xs text-zinc-500">
            1-year cumulative return for the 11 SPDR sector ETFs, with SPY as baseline.
          </p>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-2">
          <Skeleton className="h-96 w-full bg-zinc-800" />
          <Skeleton className="h-48 w-full bg-zinc-800" />
        </div>
      )}

      {!isLoading && series.length > 0 && (
        <>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <ResponsiveContainer width="100%" height={420}>
              <LineChart data={series} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
                <XAxis
                  dataKey="date"
                  stroke="#71717a"
                  fontSize={11}
                  tickFormatter={(d) => String(d).slice(5)}
                />
                <YAxis
                  stroke="#71717a"
                  fontSize={11}
                  tickFormatter={(v) => `${v}%`}
                />
                <ReferenceLine y={0} stroke="#52525b" />
                <Tooltip
                  contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
                  formatter={(v) => `${Number(v).toFixed(1)}%`}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {sectors.map((sym) => (
                  <Line
                    key={sym}
                    type="monotone"
                    dataKey={sym}
                    stroke={SECTOR_COLORS[sym]}
                    dot={false}
                    strokeWidth={sym === "SPY" ? 2 : 1.2}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
              Current Ranking (1-year return)
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 text-left text-xs text-zinc-400">
                    <th className="px-3 py-2">Symbol</th>
                    <th className="px-3 py-2">Sector</th>
                    <th className="px-3 py-2 text-right">Return</th>
                  </tr>
                </thead>
                <tbody>
                  {ranking.map((r) => (
                    <tr key={r.symbol} className="border-b border-zinc-800/50">
                      <td className="px-3 py-2 font-mono text-cyan-400">{r.symbol}</td>
                      <td className="px-3 py-2 text-zinc-300">{r.label}</td>
                      <td className={cn(
                        "px-3 py-2 text-right font-mono",
                        r.return_pct >= 0 ? "text-emerald-400" : "text-red-400",
                      )}>
                        {r.return_pct >= 0 ? "+" : ""}{r.return_pct.toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
