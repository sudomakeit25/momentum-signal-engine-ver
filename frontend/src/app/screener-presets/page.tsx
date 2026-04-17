"use client";

import { useState } from "react";
import Link from "next/link";
import { Rocket } from "lucide-react";
import { usePresetStrategies, usePresetScan } from "@/hooks/use-trading";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Strategy = { key: string; label: string; description: string };
type Match = {
  symbol: string;
  price: number;
  change_pct: number;
  score: number;
  relative_strength: number;
  note: string;
};

export default function ScreenerPresetsPage() {
  const [strategy, setStrategy] = useState("");
  const { data: strategies } = usePresetStrategies();
  const { data: result, isLoading } = usePresetScan(strategy, 25);

  const list = (strategies as Strategy[] | undefined) ?? [];
  const matches = (result?.matches as Match[] | undefined) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Rocket className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Preset Screeners</h1>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((s) => (
          <button
            key={s.key}
            onClick={() => setStrategy(s.key)}
            className={cn(
              "rounded-lg border p-3 text-left transition",
              strategy === s.key
                ? "border-cyan-500 bg-cyan-950/30"
                : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700"
            )}
          >
            <div className="text-sm font-semibold">{s.label}</div>
            <div className="mt-1 text-xs text-zinc-400">{s.description}</div>
          </button>
        ))}
      </div>

      {strategy && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3 text-xs text-zinc-400">
          {isLoading ? (
            <span>Running preset scan (first run can take 10-30s)...</span>
          ) : result ? (
            <span>
              <span className="text-zinc-200">{String(result.label)}</span> - {String(result.match_count)} matches of{" "}
              {String(result.universe_size)} scanned
            </span>
          ) : null}
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full bg-zinc-800" />
          ))}
        </div>
      ) : matches.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2 text-right">Price</th>
                <th className="px-3 py-2 text-right">Change</th>
                <th className="px-3 py-2 text-right">Score</th>
                <th className="px-3 py-2 text-right">RS</th>
                <th className="px-3 py-2">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m) => (
                <tr key={m.symbol} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                  <td className="px-3 py-2">
                    <Link href={`/chart/${m.symbol}`} className="text-cyan-400 hover:underline">
                      {m.symbol}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">${m.price.toFixed(2)}</td>
                  <td
                    className={cn(
                      "px-3 py-2 text-right font-mono",
                      m.change_pct >= 0 ? "text-emerald-400" : "text-red-400"
                    )}
                  >
                    {m.change_pct >= 0 ? "+" : ""}
                    {m.change_pct.toFixed(1)}%
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-amber-400">{m.score.toFixed(0)}</td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-400">{m.relative_strength.toFixed(2)}</td>
                  <td className="px-3 py-2 text-xs text-zinc-500">{m.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : strategy && !isLoading ? (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500">
          No symbols match this strategy right now.
        </div>
      ) : !strategy ? (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500">
          Select a strategy above to run the scan.
        </div>
      ) : null}
    </div>
  );
}
