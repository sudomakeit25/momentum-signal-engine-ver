"use client";

import { useState } from "react";
import Link from "next/link";
import { Microscope } from "lucide-react";
import { useAnalyzer } from "@/hooks/use-trading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const VERDICT_COLORS: Record<string, string> = {
  strong_buy: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  buy: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  hold: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  avoid: "bg-red-500/10 text-red-400 border-red-500/30",
};

const GRADE_COLORS: Record<string, string> = {
  A: "text-emerald-400",
  B: "text-emerald-300",
  C: "text-amber-400",
  D: "text-orange-400",
  F: "text-red-400",
};

function ScoreBar({ label, value }: { label: string; value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  const barColor = clamped >= 70 ? "bg-emerald-500" : clamped >= 50 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-zinc-400">{label}</span>
        <span className="font-mono">{value.toFixed(0)}</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-zinc-800">
        <div className={cn("h-full rounded-full", barColor)} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

export default function AnalyzerPage() {
  const [symbol, setSymbol] = useState("");
  const [active, setActive] = useState("");
  const { data, isLoading, error } = useAnalyzer(active);

  const scores = data?.scores as Record<string, number> | undefined;
  const indicators = data?.indicators as Record<string, number> | undefined;
  const range = data?.range_52w as Record<string, number> | undefined;
  const strengths = (data?.strengths as string[] | undefined) ?? [];
  const weaknesses = (data?.weaknesses as string[] | undefined) ?? [];
  const errMsg = data?.error as string | undefined;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Microscope className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Stock Analyzer</h1>
      </div>

      <div className="flex items-center gap-2">
        <Input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && setActive(symbol)}
          placeholder="Symbol (e.g. AAPL)"
          className="h-8 w-36 bg-zinc-900"
        />
        <Button size="sm" onClick={() => setActive(symbol)} disabled={!symbol || isLoading}>
          {isLoading ? "Analyzing..." : "Analyze"}
        </Button>
      </div>

      {isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full bg-zinc-800" />
          <Skeleton className="h-32 w-full bg-zinc-800" />
        </div>
      )}

      {!isLoading && errMsg && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">
          {errMsg}
        </div>
      )}

      {!isLoading && !errMsg && data && scores && indicators && range && (
        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <Link href={`/chart/${data.symbol}`} className="text-2xl font-bold text-cyan-400 hover:underline">
                  {String(data.symbol)}
                </Link>
                <div className="mt-1 flex items-baseline gap-3">
                  <span className="font-mono text-lg">${Number(data.price).toFixed(2)}</span>
                  <span
                    className={cn(
                      "font-mono text-sm",
                      Number(data.change_pct) >= 0 ? "text-emerald-400" : "text-red-400"
                    )}
                  >
                    {Number(data.change_pct) >= 0 ? "+" : ""}
                    {Number(data.change_pct).toFixed(2)}%
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-center">
                  <div className={cn("text-3xl font-bold", GRADE_COLORS[String(data.grade)] ?? "text-zinc-300")}>
                    {String(data.grade)}
                  </div>
                  <div className="text-[10px] uppercase text-zinc-500">grade</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-mono">{Number(data.composite_score).toFixed(0)}</div>
                  <div className="text-[10px] uppercase text-zinc-500">score</div>
                </div>
                <span
                  className={cn(
                    "rounded-md border px-3 py-1 text-xs font-semibold uppercase",
                    VERDICT_COLORS[String(data.verdict)] ?? "border-zinc-700 text-zinc-300"
                  )}
                >
                  {String(data.verdict).replace("_", " ")}
                </span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
              <div className="text-xs font-semibold uppercase text-zinc-400">Component Scores</div>
              <ScoreBar label="Trend" value={scores.trend} />
              <ScoreBar label="Momentum" value={scores.momentum} />
              <ScoreBar label="Quality" value={scores.quality} />
              <ScoreBar label="Risk" value={scores.risk} />
              <div className="text-[10px] text-zinc-500">Trend: {String(data.trend)}</div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-2">
              <div className="text-xs font-semibold uppercase text-zinc-400">Indicators</div>
              <dl className="grid grid-cols-2 gap-y-1 text-xs">
                <dt className="text-zinc-400">EMA 9/21/50/200</dt>
                <dd className="text-right font-mono">
                  {indicators.ema9.toFixed(1)} / {indicators.ema21.toFixed(1)} / {indicators.ema50.toFixed(1)} /{" "}
                  {indicators.ema200.toFixed(1)}
                </dd>
                <dt className="text-zinc-400">RSI(14)</dt>
                <dd className="text-right font-mono">{indicators.rsi.toFixed(1)}</dd>
                <dt className="text-zinc-400">MACD Hist</dt>
                <dd className="text-right font-mono">{indicators.macd_hist.toFixed(3)}</dd>
                <dt className="text-zinc-400">ATR / ATR%</dt>
                <dd className="text-right font-mono">
                  {indicators.atr.toFixed(2)} / {indicators.atr_pct.toFixed(2)}%
                </dd>
                <dt className="text-zinc-400">RS vs SPY</dt>
                <dd className="text-right font-mono">{indicators.relative_strength.toFixed(3)}</dd>
                <dt className="text-zinc-400">Rel Volume</dt>
                <dd className="text-right font-mono">{indicators.rel_volume.toFixed(2)}x</dd>
                <dt className="text-zinc-400">52w High / Low</dt>
                <dd className="text-right font-mono">
                  ${range.high.toFixed(2)} / ${range.low.toFixed(2)}
                </dd>
                <dt className="text-zinc-400">% Off High / Above Low</dt>
                <dd className="text-right font-mono">
                  {range.pct_off_high.toFixed(1)}% / +{range.pct_above_low.toFixed(1)}%
                </dd>
              </dl>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
              <div className="mb-2 text-xs font-semibold uppercase text-emerald-300">Strengths</div>
              {strengths.length === 0 ? (
                <div className="text-xs text-zinc-500">None flagged.</div>
              ) : (
                <ul className="space-y-1 text-sm text-emerald-200">
                  {strengths.map((s, i) => (
                    <li key={i}>- {s}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4">
              <div className="mb-2 text-xs font-semibold uppercase text-red-300">Weaknesses</div>
              {weaknesses.length === 0 ? (
                <div className="text-xs text-zinc-500">None flagged.</div>
              ) : (
                <ul className="space-y-1 text-sm text-red-200">
                  {weaknesses.map((w, i) => (
                    <li key={i}>- {w}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}

      {!active && !isLoading && (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500">
          Enter a ticker and press Analyze to get a consolidated report.
        </div>
      )}

      {error && !data && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">
          Failed to load analyzer data.
        </div>
      )}
    </div>
  );
}
