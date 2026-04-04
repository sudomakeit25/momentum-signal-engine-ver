"use client";

import { useBreadth } from "@/hooks/use-breadth";

export function BreadthWidget() {
  const { data } = useBreadth();

  if (!data) return null;

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-2 text-xs">
      <span className="font-medium text-zinc-400">Market Breadth</span>
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-emerald-500" />
        <span className="text-emerald-400">{data.bullish} Bullish ({data.bullish_pct}%)</span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-red-500" />
        <span className="text-red-400">{data.bearish} Bearish</span>
      </div>
      <span className="text-zinc-500">|</span>
      <span className="text-zinc-400">{data.above_ema21_pct}% above EMA 21</span>
      <div className="h-2 w-32 overflow-hidden rounded-full bg-red-900">
        <div
          className="h-full rounded-full bg-emerald-500 transition-all"
          style={{ width: `${data.bullish_pct}%` }}
        />
      </div>
    </div>
  );
}
