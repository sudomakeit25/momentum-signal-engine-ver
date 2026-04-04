"use client";

import type { TechnicalAnalysis } from "@/types/api";

interface TechnicalAnalysisPanelProps {
  analysis: TechnicalAnalysis;
}

export function TechnicalAnalysisPanel({ analysis }: TechnicalAnalysisPanelProps) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {/* Trend Summary */}
      {analysis.trend_summary && (
        <div className="col-span-full rounded-lg border border-zinc-800 bg-zinc-900/30 p-3">
          <h3 className="mb-1 text-xs font-semibold text-zinc-400">Trend Summary</h3>
          <p className="text-sm text-zinc-200">{analysis.trend_summary}</p>
        </div>
      )}

      {/* Detected Patterns */}
      {analysis.patterns.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3">
          <h3 className="mb-2 text-xs font-semibold text-violet-400">
            Patterns ({analysis.patterns.length})
          </h3>
          <div className="space-y-2">
            {analysis.patterns.map((p, i) => (
              <div key={i} className="text-sm">
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                      p.bias === "bullish"
                        ? "bg-green-500/20 text-green-400"
                        : p.bias === "bearish"
                          ? "bg-red-500/20 text-red-400"
                          : "bg-zinc-500/20 text-zinc-400"
                    }`}
                  >
                    {p.bias}
                  </span>
                  <span className="font-medium text-zinc-200">
                    {p.pattern_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </span>
                  <span className="ml-auto text-xs text-zinc-500">
                    {Math.round(p.confidence * 100)}% conf
                  </span>
                </div>
                {p.description && (
                  <p className="mt-0.5 text-xs text-zinc-500">{p.description}</p>
                )}
                {p.target_price && (
                  <p className={`text-xs ${p.bias === "bullish" ? "text-green-400" : p.bias === "bearish" ? "text-red-400" : "text-violet-400"}`}>
                    Target: ${p.target_price.toFixed(2)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Support & Resistance */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3">
        <h3 className="mb-2 text-xs font-semibold text-zinc-400">Support & Resistance</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="mb-1 text-[10px] font-semibold text-green-400">SUPPORT</p>
            {analysis.support_levels.length === 0 && (
              <p className="text-xs text-zinc-600">None detected</p>
            )}
            {analysis.support_levels.map((l, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-green-300">${l.price.toFixed(2)}</span>
                <span className="text-zinc-600">{l.touches}t</span>
              </div>
            ))}
          </div>
          <div>
            <p className="mb-1 text-[10px] font-semibold text-red-400">RESISTANCE</p>
            {analysis.resistance_levels.length === 0 && (
              <p className="text-xs text-zinc-600">None detected</p>
            )}
            {analysis.resistance_levels.map((l, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-red-300">${l.price.toFixed(2)}</span>
                <span className="text-zinc-600">{l.touches}t</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Price Projections */}
      {analysis.projections.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3">
          <h3 className="mb-2 text-xs font-semibold text-amber-400">
            Price Targets ({analysis.projections.length})
          </h3>
          <div className="space-y-1">
            {analysis.projections.map((p, i) => (
              <div key={i} className="flex items-center justify-between gap-2 text-xs">
                <span
                  className={`min-w-[60px] ${
                    p.projection_type === "bullish"
                      ? "text-green-300"
                      : "text-red-300"
                  }`}
                >
                  ${p.price.toFixed(2)}
                </span>
                <span className="flex-1 truncate text-zinc-500">{p.reason}</span>
                {p.estimated_days && (
                  <span className="whitespace-nowrap text-zinc-500">
                    ~{p.estimated_days}d
                  </span>
                )}
                <span className="text-zinc-600">
                  {Math.round(p.confidence * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
