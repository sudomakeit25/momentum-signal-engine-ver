"use client";

import { useState } from "react";
import { Crosshair } from "lucide-react";
import { useFibonacci, useVolumeProfile, useIchimoku, usePivots, useGapFill } from "@/hooks/use-advanced";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Tool = "fibonacci" | "volume_profile" | "ichimoku" | "pivots" | "gap_fill";

export default function TechnicalPage() {
  const [symbol, setSymbol] = useState("");
  const [active, setActive] = useState("");
  const [tool, setTool] = useState<Tool>("fibonacci");

  const fib = useFibonacci(tool === "fibonacci" ? active : "");
  const vp = useVolumeProfile(tool === "volume_profile" ? active : "");
  const ich = useIchimoku(tool === "ichimoku" ? active : "");
  const piv = usePivots(tool === "pivots" ? active : "");
  const gf = useGapFill(tool === "gap_fill" ? active : "");

  const tools: { key: Tool; label: string }[] = [
    { key: "fibonacci", label: "Fibonacci" }, { key: "volume_profile", label: "Volume Profile" },
    { key: "ichimoku", label: "Ichimoku" }, { key: "pivots", label: "Pivots" }, { key: "gap_fill", label: "Gap Fill" },
  ];

  const isLoading = fib.isLoading || vp.isLoading || ich.isLoading || piv.isLoading || gf.isLoading;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Crosshair className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Technical Analysis</h1>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} onKeyDown={(e) => e.key === "Enter" && setActive(symbol)} placeholder="Symbol" className="h-8 w-28 bg-zinc-900" />
        <Button size="sm" onClick={() => setActive(symbol)} disabled={!symbol || isLoading}>Analyze</Button>
        <div className="flex gap-1">{tools.map((t) => (
          <Button key={t.key} size="sm" variant={tool === t.key ? "default" : "outline"} className="text-xs h-7" onClick={() => setTool(t.key)}>{t.label}</Button>
        ))}</div>
      </div>

      {isLoading && <Skeleton className="h-40 w-full bg-zinc-800" />}

      {/* Fibonacci */}
      {tool === "fibonacci" && fib.data && !fib.data.error && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-bold text-cyan-400">{active}</span>
            <span className={cn("text-xs", String(fib.data.trend) === "uptrend" ? "text-emerald-400" : "text-red-400")}>{String(fib.data.trend).toUpperCase()}</span>
            <span className="text-xs text-zinc-500">Current: ${String(fib.data.current)}</span>
          </div>
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
            {Object.entries(fib.data.levels as Record<string, number>).map(([level, price]) => (
              <div key={level} className={cn("rounded border border-zinc-700 p-2 text-center", Math.abs(Number(fib.data!.current) - price) < price * 0.01 ? "border-cyan-400 bg-cyan-900/20" : "")}>
                <p className="text-xs text-zinc-500">{level}</p>
                <p className="font-mono text-sm text-zinc-300">${price}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Volume Profile */}
      {tool === "volume_profile" && vp.data && !vp.data.error && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
          <div className="flex items-center gap-4 text-xs">
            <span className="text-zinc-500">POC: <span className="text-amber-400 font-mono">${String(vp.data.poc)}</span></span>
            <span className="text-zinc-500">VA High: <span className="text-zinc-300 font-mono">${String(vp.data.value_area_high)}</span></span>
            <span className="text-zinc-500">VA Low: <span className="text-zinc-300 font-mono">${String(vp.data.value_area_low)}</span></span>
          </div>
          <div className="space-y-0.5">{((vp.data.profile as { price_mid: number; volume: number }[]) || []).map((p, i) => {
            const maxVol = Math.max(...((vp.data!.profile as { volume: number }[]) || []).map((x) => x.volume));
            const width = maxVol > 0 ? (p.volume / maxVol) * 100 : 0;
            const isPoc = Math.abs(p.price_mid - Number(vp.data!.poc)) < 1;
            return (
              <div key={i} className="flex items-center gap-2 text-[10px]">
                <span className="w-14 text-right font-mono text-zinc-500">${p.price_mid.toFixed(0)}</span>
                <div className="flex-1 h-3 rounded-sm bg-zinc-800"><div className={cn("h-full rounded-sm", isPoc ? "bg-amber-400" : "bg-cyan-400/40")} style={{ width: `${width}%` }} /></div>
              </div>
            );
          })}</div>
        </div>
      )}

      {/* Ichimoku */}
      {tool === "ichimoku" && ich.data && !ich.data.error && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-sm font-bold text-cyan-400">{active}</span>
            <span className={cn("text-xs font-medium", ich.data.signal === "bullish" ? "text-emerald-400" : ich.data.signal === "bearish" ? "text-red-400" : "text-amber-400")}>{String(ich.data.signal).toUpperCase()}</span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
            <div><span className="text-zinc-500">Tenkan: </span><span className="font-mono text-zinc-300">${String(ich.data.tenkan)}</span></div>
            <div><span className="text-zinc-500">Kijun: </span><span className="font-mono text-zinc-300">${String(ich.data.kijun)}</span></div>
            <div><span className="text-zinc-500">Cloud Top: </span><span className="font-mono text-emerald-400">${String(ich.data.cloud_top)}</span></div>
            <div><span className="text-zinc-500">Cloud Bottom: </span><span className="font-mono text-red-400">${String(ich.data.cloud_bottom)}</span></div>
            <div><span className="text-zinc-500">TK Cross: </span><span className={cn("font-mono", ich.data.tk_cross === "bullish" ? "text-emerald-400" : "text-red-400")}>{String(ich.data.tk_cross)}</span></div>
            <div><span className="text-zinc-500">Price: </span><span className="font-mono text-zinc-200">${String(ich.data.current)}</span></div>
          </div>
        </div>
      )}

      {/* Pivots */}
      {tool === "pivots" && piv.data && !piv.data.error && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-7 text-center">
            {["s3", "s2", "s1", "pivot", "r1", "r2", "r3"].map((key) => (
              <div key={key} className={cn("rounded border p-2", key === "pivot" ? "border-cyan-400 bg-cyan-900/20" : key.startsWith("r") ? "border-emerald-800/30" : "border-red-800/30")}>
                <p className="text-[10px] text-zinc-500 uppercase">{key}</p>
                <p className="font-mono text-sm text-zinc-300">${String((piv.data as Record<string, unknown>)[key])}</p>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-zinc-500 text-center">Current: ${String(piv.data.current_price)} ({String(piv.data.position)})</p>
        </div>
      )}

      {/* Gap Fill */}
      {tool === "gap_fill" && gf.data && !gf.data.error && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-center">
            <div><p className="text-2xl font-bold text-cyan-400">{String(gf.data.fill_rate)}%</p><p className="text-xs text-zinc-500">Overall Fill Rate</p></div>
            <div><p className="text-2xl font-bold text-emerald-400">{String(gf.data.up_gap_fill_rate)}%</p><p className="text-xs text-zinc-500">Up Gap Fill</p></div>
            <div><p className="text-2xl font-bold text-red-400">{String(gf.data.down_gap_fill_rate)}%</p><p className="text-xs text-zinc-500">Down Gap Fill</p></div>
            <div><p className="text-2xl font-bold text-zinc-300">{String(gf.data.total_gaps)}</p><p className="text-xs text-zinc-500">Total Gaps</p></div>
          </div>
        </div>
      )}

      {!active && !isLoading && <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">Enter a symbol and select a tool to analyze.</div>}
    </div>
  );
}
