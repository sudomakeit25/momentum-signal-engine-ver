"use client";

import Link from "next/link";
import { Waves } from "lucide-react";
import { useCyclicals, Cyclical } from "@/hooks/use-cyclicals";

export function CyclicalsWidget() {
  const { data, isLoading } = useCyclicals();
  const cyclicals = data?.cyclicals ?? [];

  if (isLoading) return null;
  if (!cyclicals.length) return null;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <div className="flex items-center gap-2">
          <Waves className="h-4 w-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-zinc-100">
            Cyclical Stocks
          </h3>
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
            {cyclicals.length}
          </span>
        </div>
        <span className="text-[10px] text-zinc-500">
          Mean-reversion candidates · 1h bars, 7d
        </span>
      </div>
      <div className="divide-y divide-zinc-800">
        {cyclicals.slice(0, 10).map((c) => (
          <CyclicalRow key={c.symbol} c={c} />
        ))}
      </div>
    </div>
  );
}

function CyclicalRow({ c }: { c: Cyclical }) {
  const biasColor =
    c.bias === "BUY"
      ? "text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
      : c.bias === "SELL"
      ? "text-red-400 border-red-500/40 bg-red-500/10"
      : "text-zinc-400 border-zinc-700 bg-zinc-800/50";

  return (
    <Link
      href={`/instrument/${encodeURIComponent(c.symbol)}`}
      className="flex items-center justify-between gap-3 px-4 py-2 transition hover:bg-zinc-800/40"
    >
      <div className="flex min-w-[88px] items-center gap-3">
        <div className="font-mono text-sm font-bold text-zinc-100">
          {c.symbol}
        </div>
        <span
          className={`rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${biasColor}`}
        >
          {c.bias}
        </span>
      </div>

      <div className="flex flex-1 items-center gap-3">
        {/* Range position bar */}
        <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-zinc-800">
          <div
            className="absolute top-0 h-full w-1 rounded-full bg-cyan-400"
            style={{ left: `${c.range_position * 100}%` }}
          />
        </div>
        <div className="font-mono text-[10px] text-zinc-500">
          ${c.range_low.toFixed(2)}-${c.range_high.toFixed(2)}
        </div>
      </div>

      <div className="flex min-w-[140px] items-center justify-end gap-3 text-right">
        <div>
          <div className="font-mono text-xs text-zinc-300">
            ${c.current_price.toFixed(2)}
          </div>
          <div className="font-mono text-[10px] text-zinc-500">
            {c.cycles}x · {c.mean_amplitude_pct.toFixed(1)}%
          </div>
        </div>
        <div>
          <div className="font-mono text-xs text-cyan-400">
            {(c.cyclical_score * 100).toFixed(0)}
          </div>
          <div className="font-mono text-[10px] text-zinc-500">score</div>
        </div>
      </div>
    </Link>
  );
}
