"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Grid3x3 } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface CorrData {
  symbols: string[];
  matrix: number[][];
}

const PRESET_GROUPS: Record<string, string> = {
  "Mega Tech": "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD",
  "Sectors": "XLK,XLF,XLE,XLV,SPY,QQQ,IWM,DIA",
  "FAANG+": "AAPL,MSFT,GOOGL,AMZN,META,NFLX,NVDA,TSLA",
  "Finance": "JPM,BAC,GS,MS,WFC,C,SCHW,BLK",
  "Energy": "XOM,CVX,COP,SLB,OXY,DVN,MPC,PSX",
};

function getCorrColor(val: number): string {
  if (val >= 0.8) return "bg-emerald-600 text-white";
  if (val >= 0.5) return "bg-emerald-800/60 text-emerald-200";
  if (val >= 0.2) return "bg-emerald-900/30 text-emerald-300";
  if (val >= -0.2) return "bg-zinc-800 text-zinc-400";
  if (val >= -0.5) return "bg-red-900/30 text-red-300";
  if (val >= -0.8) return "bg-red-800/60 text-red-200";
  return "bg-red-600 text-white";
}

export default function CorrelationPage() {
  const [symbols, setSymbols] = useState("AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD");
  const [days, setDays] = useState(90);
  const [querySymbols, setQuerySymbols] = useState(symbols);

  const { data, isLoading } = useQuery({
    queryKey: ["correlation", querySymbols, days],
    queryFn: () => apiFetch<CorrData>("/correlation", { symbols: querySymbols, days }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Grid3x3 className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Correlation Matrix</h1>
      </div>

      {/* Controls */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
        <div>
          <label className="mb-1 block text-xs text-zinc-500">Symbols (comma-separated)</label>
          <input
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(PRESET_GROUPS).map(([label, syms]) => (
            <button
              key={label}
              onClick={() => { setSymbols(syms); setQuerySymbols(syms); }}
              className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {[30, 60, 90, 180, 365].map((d) => (
              <Button
                key={d}
                variant={days === d ? "default" : "outline"}
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => setDays(d)}
              >
                {d}D
              </Button>
            ))}
          </div>
          <Button size="sm" onClick={() => setQuerySymbols(symbols)} className="bg-cyan-600 hover:bg-cyan-700">
            Compute
          </Button>
        </div>
      </div>

      {/* Matrix */}
      {isLoading ? (
        <Skeleton className="h-80 w-full bg-zinc-800" />
      ) : data && data.symbols.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="text-xs">
            <thead>
              <tr>
                <th className="px-2 py-2 text-zinc-500" />
                {data.symbols.map((s) => (
                  <th key={s} className="px-2 py-2 text-center font-bold text-cyan-400 whitespace-nowrap">
                    {s}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.symbols.map((s1, i) => (
                <tr key={s1}>
                  <td className="px-2 py-2 font-bold text-cyan-400 whitespace-nowrap">{s1}</td>
                  {data.matrix[i].map((val, j) => (
                    <td
                      key={j}
                      className={cn("px-2 py-2 text-center font-mono", getCorrColor(val))}
                      title={`${s1} vs ${data.symbols[j]}: ${val.toFixed(3)}`}
                    >
                      {val.toFixed(2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
          Enter symbols and click Compute to see correlations.
        </div>
      )}

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
        <span>Legend:</span>
        <span className="rounded bg-emerald-600 px-2 py-0.5 text-white">&gt;0.8</span>
        <span className="rounded bg-emerald-800/60 px-2 py-0.5 text-emerald-200">0.5–0.8</span>
        <span className="rounded bg-zinc-800 px-2 py-0.5 text-zinc-400">-0.2–0.2</span>
        <span className="rounded bg-red-800/60 px-2 py-0.5 text-red-200">-0.5–-0.8</span>
        <span className="rounded bg-red-600 px-2 py-0.5 text-white">&lt;-0.8</span>
      </div>
    </div>
  );
}
