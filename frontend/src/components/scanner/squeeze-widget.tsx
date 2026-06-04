"use client";

import Link from "next/link";
import { Flame } from "lucide-react";
import { useShortSqueeze, SqueezeCandidate } from "@/hooks/use-short-squeeze";

export function SqueezeWidget() {
  const { data, isLoading } = useShortSqueeze();
  const candidates = data ?? [];

  if (isLoading) return null;
  if (!candidates.length) return null;

  const settlement = candidates[0]?.settlement_date;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <div className="flex items-center gap-2">
          <Flame className="h-4 w-4 text-orange-400" />
          <h3 className="text-sm font-semibold text-zinc-100">
            Short Squeeze Candidates
          </h3>
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
            {candidates.length}
          </span>
        </div>
        <span className="text-[10px] text-zinc-500">
          Days-to-cover + rising price{settlement ? ` · SI ${settlement}` : ""}
        </span>
      </div>
      <div className="divide-y divide-zinc-800">
        {candidates.slice(0, 10).map((c) => (
          <SqueezeRow key={c.symbol} c={c} />
        ))}
      </div>
    </div>
  );
}

function SqueezeRow({ c }: { c: SqueezeCandidate }) {
  // Score 0-100. Color the score by intensity.
  const scoreColor =
    c.squeeze_score >= 70
      ? "text-orange-400"
      : c.squeeze_score >= 50
      ? "text-amber-400"
      : "text-zinc-400";

  return (
    <Link
      href={`/instrument/${encodeURIComponent(c.symbol)}`}
      className="flex items-center justify-between gap-3 px-4 py-2 transition hover:bg-zinc-800/40"
    >
      <div className="flex min-w-[120px] items-center gap-3">
        <div className="font-mono text-sm font-bold text-zinc-100">
          {c.symbol}
        </div>
        <div className="font-mono text-xs text-zinc-400">
          ${c.price.toFixed(2)}
        </div>
      </div>

      <div className="flex flex-1 items-center justify-end gap-4 text-right">
        <div className="hidden sm:block">
          <div className="font-mono text-xs text-zinc-200">
            {c.days_to_cover.toFixed(1)}d
          </div>
          <div className="font-mono text-[10px] text-zinc-500">to cover</div>
        </div>
        <div>
          <div className="font-mono text-xs text-emerald-400">
            +{c.price_change_5d.toFixed(1)}%
          </div>
          <div className="font-mono text-[10px] text-zinc-500">5d</div>
        </div>
        <div className="hidden sm:block">
          <div
            className={`font-mono text-xs ${
              c.si_change_pct >= 0 ? "text-orange-400" : "text-zinc-400"
            }`}
          >
            {c.si_change_pct >= 0 ? "+" : ""}
            {c.si_change_pct.toFixed(1)}%
          </div>
          <div className="font-mono text-[10px] text-zinc-500">SI chg</div>
        </div>
        <div className="min-w-[44px]">
          <div className={`font-mono text-sm font-bold ${scoreColor}`}>
            {c.squeeze_score.toFixed(0)}
          </div>
          <div className="font-mono text-[10px] text-zinc-500">score</div>
        </div>
      </div>
    </Link>
  );
}
