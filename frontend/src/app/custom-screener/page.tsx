"use client";

import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useCustomScan, useScreenerFilters } from "@/hooks/use-trading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function CustomScreenerPage() {
  const [filters, setFilters] = useState({ min_price: 5, max_price: 500, min_volume: 500000, min_score: 40, min_rs: 0, setup_types: "", require_ema: false, top_n: 50 });
  const [active, setActive] = useState(false);
  const { data: filterOptions } = useScreenerFilters();
  const { data: results, isLoading } = useCustomScan(active ? filters : {});
  const setupTypes = (filterOptions?.setup_types as string[]) || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <SlidersHorizontal className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Custom Screener</h1>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="space-y-1"><Label className="text-xs text-zinc-400">Min Price</Label><Input type="number" value={filters.min_price} onChange={(e) => setFilters({ ...filters, min_price: Number(e.target.value) })} className="h-8 bg-zinc-900" /></div>
          <div className="space-y-1"><Label className="text-xs text-zinc-400">Max Price</Label><Input type="number" value={filters.max_price} onChange={(e) => setFilters({ ...filters, max_price: Number(e.target.value) })} className="h-8 bg-zinc-900" /></div>
          <div className="space-y-1"><Label className="text-xs text-zinc-400">Min Volume</Label><Input type="number" value={filters.min_volume} onChange={(e) => setFilters({ ...filters, min_volume: Number(e.target.value) })} className="h-8 bg-zinc-900" /></div>
          <div className="space-y-1"><Label className="text-xs text-zinc-400">Min Score</Label><Input type="number" value={filters.min_score} onChange={(e) => setFilters({ ...filters, min_score: Number(e.target.value) })} className="h-8 bg-zinc-900" /></div>
          <div className="space-y-1"><Label className="text-xs text-zinc-400">Min RS</Label><Input type="number" value={filters.min_rs} onChange={(e) => setFilters({ ...filters, min_rs: Number(e.target.value) })} className="h-8 bg-zinc-900" step="0.1" /></div>
          <div className="space-y-1"><Label className="text-xs text-zinc-400">Results</Label><Input type="number" value={filters.top_n} onChange={(e) => setFilters({ ...filters, top_n: Number(e.target.value) })} className="h-8 bg-zinc-900" /></div>
          <div className="space-y-1">
            <Label className="text-xs text-zinc-400">EMA Aligned Only</Label>
            <label className="flex items-center gap-2 pt-1"><input type="checkbox" checked={filters.require_ema} onChange={(e) => setFilters({ ...filters, require_ema: e.target.checked })} className="rounded" /><span className="text-xs text-zinc-400">Required</span></label>
          </div>
        </div>
        {setupTypes.length > 0 && (
          <div className="space-y-1">
            <Label className="text-xs text-zinc-400">Setup Types</Label>
            <div className="flex flex-wrap gap-1">{setupTypes.map((st) => (<Button key={st} size="sm" variant={filters.setup_types.includes(st) ? "default" : "outline"} className="h-6 px-2 text-[10px]" onClick={() => { const current = filters.setup_types ? filters.setup_types.split(",").filter(Boolean) : []; const next = current.includes(st) ? current.filter((s) => s !== st) : [...current, st]; setFilters({ ...filters, setup_types: next.join(",") }); }}>{st}</Button>))}</div>
          </div>
        )}
        <Button size="sm" onClick={() => setActive(true)} disabled={isLoading}>{isLoading ? "Scanning..." : "Run Scan"}</Button>
      </div>

      {isLoading ? <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10 w-full bg-zinc-800" />)}</div>
      : results && results.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400"><th className="px-3 py-2">Symbol</th><th className="px-3 py-2 text-right">Price</th><th className="px-3 py-2 text-right">Change</th><th className="px-3 py-2 text-right">Score</th><th className="px-3 py-2 text-right">RS</th><th className="px-3 py-2">Setups</th></tr></thead>
            <tbody>{results.map((r, i) => (
              <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                <td className="px-3 py-2"><Link href={`/chart/${r.symbol}`} className="text-cyan-400 hover:underline">{String(r.symbol)}</Link></td>
                <td className="px-3 py-2 text-right font-mono">${Number(r.price).toFixed(2)}</td>
                <td className={cn("px-3 py-2 text-right font-mono", Number(r.change_pct) >= 0 ? "text-emerald-400" : "text-red-400")}>{Number(r.change_pct) >= 0 ? "+" : ""}{Number(r.change_pct).toFixed(1)}%</td>
                <td className="px-3 py-2 text-right font-mono text-amber-400">{Number(r.score).toFixed(0)}</td>
                <td className="px-3 py-2 text-right font-mono text-zinc-400">{Number(r.relative_strength).toFixed(2)}</td>
                <td className="px-3 py-2 text-xs text-zinc-500">{(r.setup_types as string[]).join(", ")}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : active ? <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500">No stocks match your criteria.</div> : null}
    </div>
  );
}
