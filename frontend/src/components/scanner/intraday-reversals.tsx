"use client";

import Link from "next/link";
import { Activity } from "lucide-react";
import { useIntradayPatterns, IntradayPattern } from "@/hooks/use-intraday-patterns";

export function IntradayReversalsWidget() {
  const { data, isLoading } = useIntradayPatterns();
  const patterns = data?.patterns ?? [];

  if (isLoading) return null;
  if (!patterns.length) return null;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-zinc-100">
            Intraday Reversals
          </h3>
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
            {patterns.length}
          </span>
        </div>
        <span className="text-[10px] text-zinc-500">
          5-min bars · refreshed live
        </span>
      </div>
      <div className="divide-y divide-zinc-800">
        {patterns.slice(0, 8).map((p, i) => (
          <PatternRow key={`${p.symbol}-${p.pattern_type}-${i}`} p={p} />
        ))}
      </div>
    </div>
  );
}

function PatternRow({ p }: { p: IntradayPattern }) {
  const isBuy = p.action === "BUY";
  const actionColor = isBuy ? "text-emerald-400" : "text-red-400";
  return (
    <Link
      href={`/instrument/${encodeURIComponent(p.symbol)}`}
      className="flex items-center justify-between px-4 py-2 transition hover:bg-zinc-800/40"
    >
      <div className="flex items-center gap-3">
        <span className={`font-mono text-sm font-bold ${actionColor}`}>
          {patternGlyph(p.pattern_type)}
        </span>
        <div>
          <div className="font-mono text-sm font-bold text-zinc-100">
            {p.symbol}
          </div>
          <div className="text-[10px] uppercase tracking-wide text-zinc-500">
            {patternLabel(p.pattern_type)}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="font-mono text-xs text-zinc-300">
            ${p.trigger_price.toFixed(2)}
          </div>
          <div className="font-mono text-[10px] text-zinc-500">
            ext ${p.extreme_price.toFixed(2)}
          </div>
        </div>
        <div className="text-right">
          <div className={`font-mono text-xs ${p.move_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            {p.move_pct >= 0 ? "+" : ""}
            {p.move_pct.toFixed(1)}%
          </div>
          <div className="font-mono text-[10px] text-zinc-500">
            now {p.recovery_pct >= 0 ? "+" : ""}
            {p.recovery_pct.toFixed(1)}%
          </div>
        </div>
      </div>
    </Link>
  );
}

function patternGlyph(t: string): string {
  switch (t) {
    case "v_reversal":
      return "V↑";
    case "inverted_v":
      return "Λ↓";
    case "breakdown":
      return "↓↓";
    case "breakout":
      return "↑↑";
    default:
      return "•";
  }
}

function patternLabel(t: string): string {
  switch (t) {
    case "v_reversal":
      return "V-reversal";
    case "inverted_v":
      return "Inverted V";
    case "breakdown":
      return "Breakdown";
    case "breakout":
      return "Breakout";
    default:
      return t;
  }
}
