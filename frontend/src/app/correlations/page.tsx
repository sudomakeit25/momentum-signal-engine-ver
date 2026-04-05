"use client";

import { GitCompareArrows } from "lucide-react";
import Link from "next/link";
import { useCorrelationScan } from "@/hooks/use-analytics";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function CorrelationsPage() {
  const { data, isLoading } = useCorrelationScan(60);
  const pairs = (data || []) as Record<string, unknown>[];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <GitCompareArrows className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Correlation Alerts</h1>
        <span className="text-xs text-zinc-500">Pairs divergence detection</span>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
        Monitors rolling correlations between historically correlated pairs. When correlation breaks down or returns diverge significantly, it may signal a pairs trading opportunity.
      </div>

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-16 w-full bg-zinc-800" />)}</div>
      ) : pairs.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                <th className="px-4 py-3 font-medium">Pair</th>
                <th className="px-4 py-3 font-medium text-right">Correlation</th>
                <th className="px-4 py-3 font-medium text-right">Avg</th>
                <th className="px-4 py-3 font-medium text-right">Z-Score</th>
                <th className="px-4 py-3 font-medium text-right">Ret A</th>
                <th className="px-4 py-3 font-medium text-right">Ret B</th>
                <th className="px-4 py-3 font-medium text-right">Spread</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {pairs.map((p, i) => {
                const pair = p.pair as string[];
                const diverging = p.diverging as boolean;
                return (
                  <tr key={i} className={cn("border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30", diverging && "bg-amber-900/5")}>
                    <td className="px-4 py-3">
                      <Link href={`/chart/${pair[0]}`} className="text-cyan-400 hover:underline">{pair[0]}</Link>
                      <span className="text-zinc-600"> / </span>
                      <Link href={`/chart/${pair[1]}`} className="text-cyan-400 hover:underline">{pair[1]}</Link>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-zinc-300">{String(p.current_correlation)}</td>
                    <td className="px-4 py-3 text-right font-mono text-zinc-500">{String(p.avg_correlation)}</td>
                    <td className={cn("px-4 py-3 text-right font-mono", Math.abs(Number(p.z_score)) > 1.5 ? "text-amber-400" : "text-zinc-400")}>
                      {String(p.z_score)}
                    </td>
                    <td className={cn("px-4 py-3 text-right font-mono", Number(p.return_a) >= 0 ? "text-emerald-400" : "text-red-400")}>
                      {Number(p.return_a) >= 0 ? "+" : ""}{String(p.return_a)}%
                    </td>
                    <td className={cn("px-4 py-3 text-right font-mono", Number(p.return_b) >= 0 ? "text-emerald-400" : "text-red-400")}>
                      {Number(p.return_b) >= 0 ? "+" : ""}{String(p.return_b)}%
                    </td>
                    <td className={cn("px-4 py-3 text-right font-mono", Math.abs(Number(p.return_spread)) > 5 ? "text-amber-400" : "text-zinc-400")}>
                      {String(p.return_spread)}%
                    </td>
                    <td className="px-4 py-3">
                      {diverging ? (
                        <span className="rounded-full bg-amber-400/10 px-2 py-0.5 text-xs font-medium text-amber-400">DIVERGING</span>
                      ) : (
                        <span className="text-xs text-zinc-600">Normal</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">No correlation data available.</div>
      )}
    </div>
  );
}
