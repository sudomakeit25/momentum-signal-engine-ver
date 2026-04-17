"use client";

import { useState } from "react";
import Link from "next/link";
import { TrendingUp } from "lucide-react";
import { useMultiYearTrends } from "@/hooks/use-trading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const REGIME_COLORS: Record<string, string> = {
  secular_uptrend: "text-emerald-400",
  secular_downtrend: "text-red-400",
  range_bound: "text-amber-400",
  transitioning: "text-zinc-300",
  unknown: "text-zinc-500",
  insufficient_history: "text-zinc-500",
};

function pctClass(v: number | null | undefined) {
  if (v === null || v === undefined) return "text-zinc-500";
  return v >= 0 ? "text-emerald-400" : "text-red-400";
}

function fmtPct(v: number | null | undefined) {
  if (v === null || v === undefined) return "-";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

export default function TrendsPage() {
  const [symbol, setSymbol] = useState("");
  const [active, setActive] = useState("");
  const { data, isLoading } = useMultiYearTrends(active);

  const returns = data?.returns as Record<string, number | null> | undefined;
  const cagr = data?.cagr as Record<string, number | null> | undefined;
  const drawdowns = data?.drawdowns as Record<string, number> | undefined;
  const vol = data?.volatility as Record<string, number> | undefined;
  const ath = data?.all_time_high as Record<string, unknown> | undefined;
  const errMsg = data?.error as string | undefined;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <TrendingUp className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Multi-Year Trends</h1>
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
          {isLoading ? "Loading..." : "Analyze"}
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

      {!isLoading && !errMsg && data && returns && cagr && drawdowns && vol && ath && (
        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <Link href={`/chart/${data.symbol}`} className="text-2xl font-bold text-cyan-400 hover:underline">
                  {String(data.symbol)}
                </Link>
                <div className="mt-1 text-xs text-zinc-400">
                  ${Number(data.price).toFixed(2)} - {Number(data.years_covered).toFixed(1)}y of weekly data
                </div>
              </div>
              <div className="text-right">
                <div className={cn("text-sm font-semibold uppercase", REGIME_COLORS[String(data.regime)] ?? "text-zinc-300")}>
                  {String(data.regime).replace(/_/g, " ")}
                </div>
                <div className="text-[10px] text-zinc-500">regime</div>
              </div>
            </div>
            <div className="mt-3 text-sm text-zinc-300">{String(data.summary)}</div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="mb-3 text-xs font-semibold uppercase text-zinc-400">Returns</div>
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <dt className="text-zinc-400">1 year</dt>
                  <dd className={cn("font-mono", pctClass(returns["1y_pct"]))}>{fmtPct(returns["1y_pct"])}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-400">3 year</dt>
                  <dd className={cn("font-mono", pctClass(returns["3y_pct"]))}>{fmtPct(returns["3y_pct"])}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-400">5 year</dt>
                  <dd className={cn("font-mono", pctClass(returns["5y_pct"]))}>{fmtPct(returns["5y_pct"])}</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="mb-3 text-xs font-semibold uppercase text-zinc-400">CAGR</div>
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <dt className="text-zinc-400">3y</dt>
                  <dd className={cn("font-mono", pctClass(cagr["3y_pct"]))}>{fmtPct(cagr["3y_pct"])}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-400">5y</dt>
                  <dd className={cn("font-mono", pctClass(cagr["5y_pct"]))}>{fmtPct(cagr["5y_pct"])}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-400">All</dt>
                  <dd className={cn("font-mono", pctClass(cagr["all_pct"]))}>{fmtPct(cagr["all_pct"])}</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="mb-3 text-xs font-semibold uppercase text-zinc-400">Risk</div>
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <dt className="text-zinc-400">Max DD (all)</dt>
                  <dd className="font-mono text-red-400">{fmtPct(drawdowns.max_pct_all)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-400">Max DD (3y)</dt>
                  <dd className="font-mono text-red-400">{fmtPct(drawdowns.max_pct_3y)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-400">Ann. Vol</dt>
                  <dd className="font-mono text-amber-400">{fmtPct(vol.annualized_pct)}</dd>
                </div>
              </dl>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">All-Time High</div>
              <div className="flex items-baseline justify-between">
                <div className="font-mono text-lg">${Number(ath.price).toFixed(2)}</div>
                <div className="text-xs text-zinc-500">{String(ath.date).slice(0, 10)}</div>
              </div>
              <div className={cn("mt-1 font-mono text-sm", pctClass(Number(ath.pct_off)))}>
                {fmtPct(Number(ath.pct_off))} from ATH
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">Relative Strength</div>
              <div className="text-sm">
                3y vs SPY:{" "}
                {data.rs_vs_spy_3y_pct_points === null || data.rs_vs_spy_3y_pct_points === undefined ? (
                  <span className="text-zinc-500">n/a</span>
                ) : (
                  <span className={cn("font-mono", pctClass(Number(data.rs_vs_spy_3y_pct_points)))}>
                    {fmtPct(Number(data.rs_vs_spy_3y_pct_points))} pts
                  </span>
                )}
              </div>
              <div className="mt-1 text-[10px] text-zinc-500">
                Difference in 3-year total return vs SPY.
              </div>
            </div>
          </div>
        </div>
      )}

      {!active && !isLoading && (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500">
          Enter a ticker to see 1y / 3y / 5y trend statistics.
        </div>
      )}
    </div>
  );
}
