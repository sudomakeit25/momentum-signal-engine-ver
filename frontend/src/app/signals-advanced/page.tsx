"use client";

import { useState } from "react";
import { Zap } from "lucide-react";
import Link from "next/link";
import { useVix, useGaps, useUnusualVolume, useShortSqueeze, useBollingerSqueeze, useMacdDivergence, useEmaCrosses, useAtrRanking } from "@/hooks/use-advanced";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Tab = "vix" | "gaps" | "volume" | "squeeze" | "bollinger" | "macd" | "crosses" | "atr";

function DataTable({ data, columns }: { data: Record<string, unknown>[]; columns: { key: string; label: string; align?: string; color?: (v: unknown) => string }[] }) {
  if (!data?.length) return <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500">No data available.</div>;
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-sm">
        <thead><tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">{columns.map((c) => <th key={c.key} className={cn("px-3 py-2 font-medium", c.align === "right" && "text-right")}>{c.label}</th>)}</tr></thead>
        <tbody>{data.map((row, i) => (
          <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">{columns.map((c) => {
            const val = row[c.key];
            const color = c.color ? c.color(val) : "text-zinc-300";
            const isSymbol = c.key === "symbol";
            return <td key={c.key} className={cn("px-3 py-2 font-mono text-xs", c.align === "right" && "text-right", color)}>
              {isSymbol ? <Link href={`/chart/${val}`} className="text-cyan-400 hover:underline">{String(val)}</Link> : String(val ?? "-")}
            </td>;
          })}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export default function SignalsAdvancedPage() {
  const [tab, setTab] = useState<Tab>("gaps");
  const vix = useVix();
  const gaps = useGaps();
  const volume = useUnusualVolume();
  const squeeze = useShortSqueeze();
  const bollinger = useBollingerSqueeze();
  const macd = useMacdDivergence();
  const crosses = useEmaCrosses();
  const atr = useAtrRanking();

  const tabs: { key: Tab; label: string }[] = [
    { key: "vix", label: "VIX" }, { key: "gaps", label: "Gaps" }, { key: "volume", label: "Volume" },
    { key: "squeeze", label: "Short Squeeze" }, { key: "bollinger", label: "BB Squeeze" },
    { key: "macd", label: "MACD Div" }, { key: "crosses", label: "EMA Cross" }, { key: "atr", label: "ATR" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Zap className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Advanced Signals</h1>
      </div>

      {/* VIX Banner */}
      {vix.data && (
        <div className={cn("rounded-lg border p-3 text-sm flex items-center justify-between",
          vix.data.level === "high" ? "border-red-800/30 bg-red-900/10 text-red-400" :
          vix.data.level === "low" ? "border-emerald-800/30 bg-emerald-900/10 text-emerald-400" :
          "border-zinc-800 bg-zinc-900/50 text-zinc-400"
        )}>
          <span>{String(vix.data.description)}</span>
          <span className="font-mono text-xs">Confidence adj: {String(vix.data.confidence_adjustment)}x</span>
        </div>
      )}

      <div className="flex flex-wrap gap-1">{tabs.map((t) => (
        <Button key={t.key} size="sm" variant={tab === t.key ? "default" : "outline"} className="text-xs h-7" onClick={() => setTab(t.key)}>{t.label}</Button>
      ))}</div>

      {tab === "gaps" && (gaps.isLoading ? <Skeleton className="h-40 bg-zinc-800" /> :
        <DataTable data={(gaps.data || []) as Record<string, unknown>[]} columns={[
          { key: "symbol", label: "Symbol" },
          { key: "gap_pct", label: "Gap %", align: "right", color: (v) => Number(v) >= 0 ? "text-emerald-400" : "text-red-400" },
          { key: "prev_close", label: "Prev Close", align: "right" },
          { key: "open", label: "Open", align: "right" },
          { key: "current", label: "Current", align: "right" },
          { key: "direction", label: "Dir", color: (v) => v === "up" ? "text-emerald-400" : "text-red-400" },
          { key: "filled", label: "Filled", color: (v) => v ? "text-amber-400" : "text-zinc-600" },
        ]} />
      )}

      {tab === "volume" && (volume.isLoading ? <Skeleton className="h-40 bg-zinc-800" /> :
        <DataTable data={(volume.data || []) as Record<string, unknown>[]} columns={[
          { key: "symbol", label: "Symbol" },
          { key: "ratio", label: "Vol Ratio", align: "right", color: () => "text-amber-400" },
          { key: "volume", label: "Volume", align: "right" },
          { key: "avg_volume", label: "Avg Vol", align: "right" },
          { key: "price", label: "Price", align: "right" },
          { key: "change_pct", label: "Change", align: "right", color: (v) => Number(v) >= 0 ? "text-emerald-400" : "text-red-400" },
        ]} />
      )}

      {tab === "squeeze" && (squeeze.isLoading ? <Skeleton className="h-40 bg-zinc-800" /> :
        <DataTable data={(squeeze.data || []) as Record<string, unknown>[]} columns={[
          { key: "symbol", label: "Symbol" },
          { key: "avg_short_pct", label: "Short %", align: "right", color: () => "text-red-400" },
          { key: "price_change_5d", label: "5d Change", align: "right", color: (v) => Number(v) >= 0 ? "text-emerald-400" : "text-red-400" },
          { key: "squeeze_score", label: "Score", align: "right", color: () => "text-amber-400" },
          { key: "price", label: "Price", align: "right" },
        ]} />
      )}

      {tab === "bollinger" && (bollinger.isLoading ? <Skeleton className="h-40 bg-zinc-800" /> :
        <DataTable data={(bollinger.data || []) as Record<string, unknown>[]} columns={[
          { key: "symbol", label: "Symbol" },
          { key: "squeeze_ratio", label: "Squeeze", align: "right", color: () => "text-amber-400" },
          { key: "bandwidth", label: "BW", align: "right" },
          { key: "price", label: "Price", align: "right" },
          { key: "upper_band", label: "Upper", align: "right" },
          { key: "lower_band", label: "Lower", align: "right" },
        ]} />
      )}

      {tab === "macd" && (macd.isLoading ? <Skeleton className="h-40 bg-zinc-800" /> :
        <DataTable data={(macd.data || []) as Record<string, unknown>[]} columns={[
          { key: "symbol", label: "Symbol" },
          { key: "type", label: "Type", color: (v) => v === "bullish" ? "text-emerald-400" : "text-red-400" },
          { key: "price_change", label: "Price Chg", align: "right", color: (v) => Number(v) >= 0 ? "text-emerald-400" : "text-red-400" },
          { key: "price", label: "Price", align: "right" },
          { key: "description", label: "Signal" },
        ]} />
      )}

      {tab === "crosses" && (crosses.isLoading ? <Skeleton className="h-40 bg-zinc-800" /> :
        <DataTable data={(crosses.data || []) as Record<string, unknown>[]} columns={[
          { key: "symbol", label: "Symbol" },
          { key: "type", label: "Type", color: (v) => String(v).includes("golden") ? "text-emerald-400" : "text-red-400" },
          { key: "price", label: "Price", align: "right" },
          { key: "ema50", label: "EMA50", align: "right" },
          { key: "ema200", label: "EMA200", align: "right" },
          { key: "bars_ago", label: "Days Ago", align: "right" },
        ]} />
      )}

      {tab === "atr" && (atr.isLoading ? <Skeleton className="h-40 bg-zinc-800" /> :
        <DataTable data={(atr.data || []).slice(0, 30) as Record<string, unknown>[]} columns={[
          { key: "symbol", label: "Symbol" },
          { key: "atr_pct", label: "ATR %", align: "right", color: () => "text-amber-400" },
          { key: "atr", label: "ATR $", align: "right" },
          { key: "price", label: "Price", align: "right" },
        ]} />
      )}

      {tab === "vix" && vix.data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(vix.data as Record<string, unknown>).filter(([k]) => k !== "description").map(([k, v]) => (
            <div key={k} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
              <p className="text-lg font-bold text-zinc-200">{String(v)}</p>
              <p className="text-[10px] text-zinc-500">{k.replace(/_/g, " ")}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
