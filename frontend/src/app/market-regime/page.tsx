"use client";

import { Gauge } from "lucide-react";
import { useMarketRegime } from "@/hooks/use-analytics";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const REGIME_COLORS: Record<string, string> = {
  strong_uptrend: "text-emerald-400",
  uptrend: "text-emerald-400",
  strong_downtrend: "text-red-400",
  downtrend: "text-red-400",
  volatile_trending: "text-amber-400",
  volatile_choppy: "text-orange-400",
  range_bound: "text-zinc-400",
  transitional: "text-zinc-400",
};

export default function MarketRegimePage() {
  const { data, isLoading } = useMarketRegime();
  const regime = data as Record<string, unknown> | undefined;
  const components = regime?.components as Record<string, unknown> | undefined;
  const rec = regime?.recommendation as Record<string, string> | undefined;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Gauge className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Market Regime</h1>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
        Classifies the current market using SPY trend strength, volatility, breadth, and momentum. Adjusts signal confidence recommendations based on conditions.
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full bg-zinc-800" />
      ) : regime ? (
        <div className="space-y-4">
          {/* Main regime card */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 text-center">
            <p className={cn("text-3xl font-bold", REGIME_COLORS[String(regime.regime)] || "text-zinc-300")}>
              {String(regime.regime).replace(/_/g, " ").toUpperCase()}
            </p>
            <p className="mt-2 text-sm text-zinc-400">{String(regime.description)}</p>
            <div className="mt-3 flex items-center justify-center gap-4 text-xs">
              <span className="text-zinc-500">SPY: <span className="text-zinc-300">${String(regime.spy_price)}</span></span>
              <span className="text-zinc-500">20d: <span className={Number(regime.spy_change_20d) >= 0 ? "text-emerald-400" : "text-red-400"}>{Number(regime.spy_change_20d) >= 0 ? "+" : ""}{String(regime.spy_change_20d)}%</span></span>
              <span className="text-zinc-500">Confidence Adj: <span className="text-cyan-400">{String(regime.confidence_adjustment)}x</span></span>
            </div>
          </div>

          {/* Components */}
          {components && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
                <p className="text-lg font-bold text-zinc-200">{String(components.trend_strength)}</p>
                <p className="text-xs text-zinc-500">Trend Strength</p>
                <p className="mt-1 text-[10px] text-zinc-600">{String(components.trend_direction)}</p>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
                <p className={cn("text-lg font-bold", components.volatility_level === "high" ? "text-red-400" : components.volatility_level === "moderate" ? "text-amber-400" : "text-emerald-400")}>
                  {String(components.volatility)}
                </p>
                <p className="text-xs text-zinc-500">Volatility</p>
                <p className="mt-1 text-[10px] text-zinc-600">{String(components.volatility_level)}</p>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
                <p className={cn("text-lg font-bold", Number(components.breadth) > 0 ? "text-emerald-400" : "text-red-400")}>
                  {String(components.breadth)}
                </p>
                <p className="text-xs text-zinc-500">Breadth</p>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
                <p className={cn("text-lg font-bold", Number(components.momentum) > 0 ? "text-emerald-400" : "text-red-400")}>
                  {String(components.momentum)}
                </p>
                <p className="text-xs text-zinc-500">Momentum</p>
              </div>
            </div>
          )}

          {/* Recommendations */}
          {rec && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <h2 className="text-sm font-medium text-zinc-300">Recommendations</h2>
              <div className="mt-2 grid grid-cols-3 gap-4 text-xs">
                <div>
                  <span className="text-zinc-500">Bias: </span>
                  <span className={cn("font-medium", rec.bias === "long" ? "text-emerald-400" : rec.bias === "short" ? "text-red-400" : "text-zinc-300")}>
                    {rec.bias.toUpperCase()}
                  </span>
                </div>
                <div>
                  <span className="text-zinc-500">Position Size: </span>
                  <span className="font-medium text-zinc-300">{rec.position_size}</span>
                </div>
                <div>
                  <span className="text-zinc-500">Stop Width: </span>
                  <span className="font-medium text-zinc-300">{rec.stop_width}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">Unable to detect market regime.</div>
      )}
    </div>
  );
}
