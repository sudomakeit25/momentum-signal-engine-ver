"use client";

import { useState } from "react";
import Link from "next/link";
import { LayoutGrid } from "lucide-react";
import { useScan } from "@/hooks/use-scan";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ScanResult } from "@/types/api";

type ColorBy = "change" | "score" | "rs";

function getTileColor(result: ScanResult, colorBy: ColorBy): string {
  if (colorBy === "change") {
    const v = result.change_pct;
    if (v >= 5) return "bg-emerald-500";
    if (v >= 3) return "bg-emerald-600";
    if (v >= 1) return "bg-emerald-700";
    if (v >= 0) return "bg-emerald-900";
    if (v >= -1) return "bg-red-900";
    if (v >= -3) return "bg-red-700";
    if (v >= -5) return "bg-red-600";
    return "bg-red-500";
  }
  if (colorBy === "score") {
    const s = result.score;
    if (s >= 80) return "bg-emerald-500";
    if (s >= 70) return "bg-emerald-600";
    if (s >= 60) return "bg-emerald-700";
    if (s >= 50) return "bg-yellow-700";
    if (s >= 40) return "bg-yellow-800";
    return "bg-zinc-700";
  }
  // RS
  const rs = result.relative_strength;
  if (rs >= 1.3) return "bg-emerald-500";
  if (rs >= 1.15) return "bg-emerald-600";
  if (rs >= 1.05) return "bg-emerald-700";
  if (rs >= 0.95) return "bg-yellow-700";
  if (rs >= 0.85) return "bg-red-700";
  return "bg-red-600";
}

function getTileLabel(result: ScanResult, colorBy: ColorBy): string {
  if (colorBy === "change") return `${result.change_pct >= 0 ? "+" : ""}${result.change_pct.toFixed(1)}%`;
  if (colorBy === "score") return result.score.toFixed(0);
  return result.relative_strength.toFixed(2);
}

export default function HeatmapPage() {
  const [colorBy, setColorBy] = useState<ColorBy>("change");
  const { data, isLoading } = useScan({ top: 76 });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <LayoutGrid className="h-5 w-5 text-cyan-400" />
          <h1 className="text-lg font-bold">Market Heatmap</h1>
        </div>
        <div className="flex gap-2">
          {(["change", "score", "rs"] as ColorBy[]).map((key) => (
            <Button
              key={key}
              variant={colorBy === key ? "default" : "outline"}
              size="sm"
              onClick={() => setColorBy(key)}
              className="text-xs"
            >
              {key === "change" ? "Change %" : key === "score" ? "Score" : "Rel Strength"}
            </Button>
          ))}
        </div>
      </div>

      {isLoading && !data ? (
        <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10">
          {Array.from({ length: 40 }).map((_, i) => (
            <Skeleton key={i} className="aspect-square bg-zinc-800" />
          ))}
        </div>
      ) : data && data.length > 0 ? (
        <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10">
          {data.map((r) => (
            <Link
              key={r.symbol}
              href={`/chart/${r.symbol}`}
              className={cn(
                "flex flex-col items-center justify-center rounded-md p-2 transition-transform hover:scale-105 hover:ring-2 hover:ring-cyan-400",
                getTileColor(r, colorBy)
              )}
            >
              <span className="text-xs font-bold text-white">{r.symbol}</span>
              <span className="text-[10px] text-white/80">
                {getTileLabel(r, colorBy)}
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          No data available.
        </div>
      )}
    </div>
  );
}
