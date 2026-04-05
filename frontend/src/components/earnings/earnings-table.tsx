"use client";

import Link from "next/link";
import type { EarningsConviction } from "@/types/api";
import { ConvictionBadge } from "./conviction-badge";
import { cn } from "@/lib/utils";

function SentimentChip({ value }: { value: string }) {
  const colorMap: Record<string, string> = {
    buying: "text-emerald-400",
    selling: "text-red-400",
    up: "text-emerald-400",
    down: "text-red-400",
    neutral: "text-zinc-500",
    stable: "text-zinc-500",
  };

  return (
    <span className={cn("text-xs font-medium", colorMap[value] || "text-zinc-500")}>
      {value.charAt(0).toUpperCase() + value.slice(1)}
    </span>
  );
}

function SurpriseBar({ values }: { values: number[] }) {
  if (!values.length) return <span className="text-xs text-zinc-500">-</span>;
  return (
    <div className="flex items-center gap-0.5">
      {values.slice(0, 6).map((v, i) => (
        <div
          key={i}
          className={cn(
            "h-4 w-1.5 rounded-sm",
            v > 0 ? "bg-emerald-400" : v < 0 ? "bg-red-400" : "bg-zinc-600"
          )}
          title={`${v > 0 ? "+" : ""}${v.toFixed(1)}%`}
        />
      ))}
    </div>
  );
}

export function EarningsTable({ results }: { results: EarningsConviction[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
            <th className="px-4 py-3 font-medium">Symbol</th>
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 font-medium">Conviction</th>
            <th className="px-4 py-3 font-medium">EPS History</th>
            <th className="px-4 py-3 font-medium">Insiders</th>
            <th className="px-4 py-3 font-medium">Revisions</th>
            <th className="px-4 py-3 font-medium">Signal</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => {
            const date = new Date(r.earnings_date);
            const daysAway = Math.ceil(
              (date.getTime() - Date.now()) / (1000 * 60 * 60 * 24)
            );
            return (
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
                <td className="px-4 py-3 text-xs">
                  <span className="text-zinc-300">
                    {date.toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                  <span className="ml-1 text-zinc-500">
                    ({daysAway}d)
                  </span>
                </td>
                <td className="px-4 py-3">
                  <ConvictionBadge score={r.conviction_score} />
                </td>
                <td className="px-4 py-3">
                  <SurpriseBar values={r.eps_surprise_history} />
                </td>
                <td className="px-4 py-3">
                  <SentimentChip value={r.insider_sentiment}  />
                </td>
                <td className="px-4 py-3">
                  <SentimentChip value={r.analyst_revisions}  />
                </td>
                <td className="px-4 py-3 max-w-[200px] truncate text-xs text-zinc-500">
                  {r.alert_reasons.length > 0 ? r.alert_reasons[0] : "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
