"use client";

import { useState } from "react";
import { Layers } from "lucide-react";
import { useMultiTimeframe } from "@/hooks/use-trading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const TREND_COLORS: Record<string, string> = {
  bullish: "text-emerald-400",
  turning_bullish: "text-emerald-300",
  bearish: "text-red-400",
  turning_bearish: "text-red-300",
  neutral: "text-zinc-400",
};

export default function MultiTimeframePage() {
  const [symbol, setSymbol] = useState("");
  const [active, setActive] = useState("");
  const { data, isLoading } = useMultiTimeframe(active);
  const tf = data?.timeframes as Record<string, Record<string, unknown>> | undefined;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Layers className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Multi-Timeframe Analysis</h1>
      </div>

      <div className="flex items-center gap-2">
        <Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} onKeyDown={(e) => e.key === "Enter" && setActive(symbol)} placeholder="Symbol (e.g. AAPL)" className="h-8 w-36 bg-zinc-900" />
        <Button size="sm" onClick={() => setActive(symbol)} disabled={!symbol || isLoading}>{isLoading ? "Analyzing..." : "Analyze"}</Button>
      </div>

      {isLoading && <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32 w-full bg-zinc-800" />)}</div>}

      {data && tf && (
        <div className="space-y-4">
          {/* Alignment */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
            <p className="text-xs text-zinc-500">Timeframe Alignment</p>
            <p className={cn("text-2xl font-bold", data.alignment === "bullish" ? "text-emerald-400" : data.alignment === "bearish" ? "text-red-400" : "text-zinc-400")}>
              {String(data.alignment).toUpperCase()}
            </p>
            <p className="mt-1 text-xs text-zinc-500">{String(data.recommendation)}</p>
          </div>

          {/* Timeframe Cards */}
          <div className="grid gap-3 sm:grid-cols-3">
            {["weekly", "daily", "hourly"].map((tfKey) => {
              const t = tf[tfKey];
              if (!t) return null;
              return (
                <div key={tfKey} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-zinc-300">{String(t.label)}</span>
                    <span className={cn("text-xs font-medium", TREND_COLORS[String(t.trend)] || "text-zinc-500")}>
                      {String(t.trend).replace(/_/g, " ").toUpperCase()}
                    </span>
                  </div>
                  {Number(t.price) > 0 && (
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div><span className="text-zinc-500">Price: </span><span className="font-mono text-zinc-300">${Number(t.price).toFixed(2)}</span></div>
                      <div><span className="text-zinc-500">RSI: </span><span className={cn("font-mono", Number(t.rsi) > 70 ? "text-red-400" : Number(t.rsi) < 30 ? "text-emerald-400" : "text-zinc-300")}>{String(t.rsi)}</span></div>
                      <div><span className="text-zinc-500">EMA9: </span><span className="font-mono text-zinc-400">{String(t.ema9)}</span></div>
                      <div><span className="text-zinc-500">EMA21: </span><span className="font-mono text-zinc-400">{String(t.ema21)}</span></div>
                      <div><span className="text-zinc-500">High 20: </span><span className="font-mono text-zinc-400">{String(t.high_20)}</span></div>
                      <div><span className="text-zinc-500">Low 20: </span><span className="font-mono text-zinc-400">{String(t.low_20)}</span></div>
                    </div>
                  )}
                  <p className="text-[10px] text-zinc-600">{String(t.summary)}</p>
                  {Number(t.signal_count) > 0 && <p className="text-xs text-amber-400">{String(t.signal_count)} signals</p>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!active && !isLoading && <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">Enter a symbol to see weekly, daily, and hourly analysis side by side.</div>}
    </div>
  );
}
