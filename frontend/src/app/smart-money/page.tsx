"use client";

import { RefreshCw, Target } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSmartMoney } from "@/hooks/use-smart-money";
import type { SmartMoneyResult } from "@/hooks/use-smart-money";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SOURCE_COLORS: Record<string, string> = {
  dark_pool: "bg-purple-400/10 text-purple-400 border-purple-400/20",
  options_flow: "bg-cyan-400/10 text-cyan-400 border-cyan-400/20",
  earnings: "bg-amber-400/10 text-amber-400 border-amber-400/20",
  momentum: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
};

const SOURCE_LABELS: Record<string, string> = {
  dark_pool: "Dark Pool",
  options_flow: "Options",
  earnings: "Earnings",
  momentum: "Momentum",
};

function SourceBadge({
  source,
  sentiment,
}: {
  source: string;
  sentiment: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
        SOURCE_COLORS[source] || "bg-zinc-400/10 text-zinc-400 border-zinc-400/20"
      )}
    >
      {sentiment === "bullish" ? "+" : sentiment === "bearish" ? "-" : "~"}
      {SOURCE_LABELS[source] || source}
    </span>
  );
}

function ScoreBar({ score }: { score: number }) {
  const color =
    score >= 70
      ? "bg-emerald-400"
      : score >= 50
        ? "bg-amber-400"
        : "bg-zinc-500";

  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-20 rounded-full bg-zinc-800">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${Math.min(score, 100)}%` }}
        />
      </div>
      <span className="font-mono text-xs text-zinc-300">
        {score.toFixed(0)}
      </span>
    </div>
  );
}

function ConvergenceCard({ result }: { result: SmartMoneyResult }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-zinc-700">
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <Link
              href={`/chart/${result.symbol}`}
              className="text-lg font-bold text-cyan-400 hover:underline"
            >
              {result.symbol}
            </Link>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-medium",
                result.direction === "bullish"
                  ? "bg-emerald-400/10 text-emerald-400"
                  : result.direction === "bearish"
                    ? "bg-red-400/10 text-red-400"
                    : "bg-zinc-400/10 text-zinc-400"
              )}
            >
              {result.direction.toUpperCase()}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {result.signals.map((s, i) => (
              <SourceBadge key={i} source={s.source} sentiment={s.sentiment} />
            ))}
          </div>
        </div>
        <ScoreBar score={result.convergence_score} />
      </div>

      <div className="mt-3 space-y-1">
        {result.signals.map((s, i) => (
          <p key={i} className="text-xs text-zinc-400">
            {s.detail}
          </p>
        ))}
      </div>
    </div>
  );
}

export default function SmartMoneyPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, dataUpdatedAt } = useSmartMoney();

  const updatedAt = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null;

  const bullish = data?.filter((r) => r.direction === "bullish") || [];
  const bearish = data?.filter((r) => r.direction === "bearish") || [];
  const neutral = data?.filter((r) => r.direction === "neutral") || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Target className="h-5 w-5 text-cyan-400" />
          <h1 className="text-lg font-bold">Smart Money</h1>
          <span className="text-xs text-zinc-500">
            Multi-signal convergence
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              queryClient.invalidateQueries({ queryKey: ["smart-money"] })
            }
            disabled={isLoading}
            className="gap-2 text-xs"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
          {updatedAt && (
            <span className="text-xs text-zinc-500">
              Updated {updatedAt}
            </span>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
        Finds stocks where multiple smart money indicators align: dark pool
        accumulation, unusual options flow, earnings conviction, and momentum
        signals. Stocks appearing here have 2+ confirming signals pointing
        in the same direction.
      </div>

      {/* Summary Stats */}
      {data && data.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-emerald-800/30 bg-emerald-900/10 p-3 text-center">
            <p className="text-2xl font-bold text-emerald-400">
              {bullish.length}
            </p>
            <p className="text-xs text-zinc-400">Bullish</p>
          </div>
          <div className="rounded-lg border border-red-800/30 bg-red-900/10 p-3 text-center">
            <p className="text-2xl font-bold text-red-400">
              {bearish.length}
            </p>
            <p className="text-xs text-zinc-400">Bearish</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
            <p className="text-2xl font-bold text-zinc-400">
              {neutral.length}
            </p>
            <p className="text-xs text-zinc-400">Mixed</p>
          </div>
        </div>
      )}

      {isError ? (
        <div className="rounded-lg border border-red-800/30 bg-red-900/10 p-8 text-center">
          <p className="text-sm text-zinc-300">Failed to load data.</p>
          <button onClick={() => queryClient.invalidateQueries({ queryKey: ["smart-money"] })} className="mt-3 text-xs text-cyan-400 hover:underline">Try again</button>
        </div>
      ) : isLoading && !data ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <svg
              className="h-5 w-5 animate-spin text-cyan-400"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <div>
              <p className="text-sm font-medium text-zinc-200">
                Analyzing smart money convergence...
              </p>
              <p className="text-xs text-zinc-500">
                Cross-referencing dark pool, options, earnings, and momentum
                data
              </p>
            </div>
          </div>
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full bg-zinc-800" />
            ))}
          </div>
        </div>
      ) : data && data.length > 0 ? (
        <div className="space-y-3">
          {data.map((result) => (
            <ConvergenceCard key={result.symbol} result={result} />
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          No convergence signals found. This requires data from at least 2 of:
          Dark Pool, Options Flow, Earnings, and Momentum scanners. Make sure
          you have visited those pages first to populate the cache.
        </div>
      )}
    </div>
  );
}
