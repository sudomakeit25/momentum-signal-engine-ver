"use client";

import Link from "next/link";
import type { DarkPoolResult } from "@/types/api";
import { cn } from "@/lib/utils";

function TrendBadge({ trend, strength }: { trend: string; strength: number }) {
  const color =
    trend === "accumulating"
      ? "text-emerald-400 bg-emerald-400/10"
      : trend === "distributing"
        ? "text-red-400 bg-red-400/10"
        : "text-zinc-400 bg-zinc-400/10";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        color
      )}
    >
      {trend === "accumulating" ? "+" : trend === "distributing" ? "-" : "~"}
      {trend.charAt(0).toUpperCase() + trend.slice(1)}
      {strength > 0 && (
        <span className="text-[10px] opacity-70">
          {(strength * 100).toFixed(0)}%
        </span>
      )}
    </span>
  );
}

export function DarkPoolTable({ results }: { results: DarkPoolResult[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
            <th className="px-4 py-3 font-medium">Symbol</th>
            <th className="px-4 py-3 font-medium text-right">Short Vol %</th>
            <th className="px-4 py-3 font-medium text-right">Avg %</th>
            <th className="px-4 py-3 font-medium text-right">Price Chg</th>
            <th className="px-4 py-3 font-medium">Trend</th>
            <th className="px-4 py-3 font-medium">Signal</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr
              key={r.symbol}
              className="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30"
            >
              <td className="px-4 py-3">
                <Link
                  href={`/chart/${r.symbol}`}
                  className="font-medium text-cyan-400 hover:underline"
                >
                  {r.symbol}
                </Link>
              </td>
              <td
                className={cn(
                  "px-4 py-3 text-right font-mono",
                  r.recent_short_pct > r.avg_short_pct
                    ? "text-amber-400"
                    : "text-zinc-300"
                )}
              >
                {r.recent_short_pct.toFixed(1)}%
              </td>
              <td className="px-4 py-3 text-right font-mono text-zinc-400">
                {r.avg_short_pct.toFixed(1)}%
              </td>
              <td
                className={cn(
                  "px-4 py-3 text-right font-mono",
                  r.price_change_pct >= 0 ? "text-emerald-400" : "text-red-400"
                )}
              >
                {r.price_change_pct >= 0 ? "+" : ""}
                {r.price_change_pct.toFixed(1)}%
              </td>
              <td className="px-4 py-3">
                <TrendBadge trend={r.trend} strength={r.trend_strength} />
              </td>
              <td className="px-4 py-3 text-xs text-zinc-500">
                {r.alert_reasons.length > 0
                  ? r.alert_reasons[0].split("--")[1]?.trim() || r.alert_reasons[0]
                  : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
