"use client";

import { useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function ComparePage() {
  const [input, setInput] = useState("AAPL,MSFT,GOOGL");
  const [active, setActive] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["compare", active],
    queryFn: () => apiFetch<{ stocks: Record<string, unknown>[] }>("/compare", { symbols: active }),
    enabled: !!active,
  });

  const stocks = data?.stocks || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <ArrowLeftRight className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Stock Comparison</h1>
      </div>

      <div className="flex items-center gap-2">
        <Input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())} placeholder="AAPL,MSFT,GOOGL" className="h-8 w-64 bg-zinc-900" onKeyDown={(e) => e.key === "Enter" && setActive(input)} />
        <Button size="sm" onClick={() => setActive(input)} disabled={!input || isLoading}>{isLoading ? "Loading..." : "Compare"}</Button>
      </div>

      {isLoading && <Skeleton className="h-40 bg-zinc-800" />}

      {stocks.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                <th className="px-3 py-2">Metric</th>
                {stocks.map((s) => <th key={String(s.symbol)} className="px-3 py-2 text-right"><Link href={`/chart/${s.symbol}`} className="text-cyan-400 hover:underline">{String(s.symbol)}</Link></th>)}
              </tr>
            </thead>
            <tbody>
              {[
                { key: "price", label: "Price", fmt: (v: unknown) => `$${Number(v).toFixed(2)}` },
                { key: "change_1d", label: "1D Change", fmt: (v: unknown) => `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(2)}%`, color: true },
                { key: "change_5d", label: "5D Change", fmt: (v: unknown) => `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(2)}%`, color: true },
                { key: "change_20d", label: "20D Change", fmt: (v: unknown) => `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(2)}%`, color: true },
                { key: "change_60d", label: "60D Change", fmt: (v: unknown) => `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(2)}%`, color: true },
                { key: "pct_from_high", label: "From 52w High", fmt: (v: unknown) => `${Number(v).toFixed(1)}%`, color: true },
                { key: "high_52w", label: "52w High", fmt: (v: unknown) => `$${Number(v).toFixed(2)}` },
                { key: "low_52w", label: "52w Low", fmt: (v: unknown) => `$${Number(v).toFixed(2)}` },
                { key: "avg_volume", label: "Avg Volume", fmt: (v: unknown) => Number(v).toLocaleString() },
                { key: "trend", label: "Trend", fmt: (v: unknown) => String(v).toUpperCase(), color: true },
              ].map((row) => (
                <tr key={row.key} className="border-b border-zinc-800/30">
                  <td className="px-3 py-2 text-xs text-zinc-500">{row.label}</td>
                  {stocks.map((s) => {
                    const val = s[row.key];
                    const formatted = row.fmt(val);
                    return (
                      <td key={String(s.symbol)} className={cn("px-3 py-2 text-right font-mono text-xs",
                        row.color ? (String(val) === "bullish" || Number(val) > 0 ? "text-emerald-400" : String(val) === "bearish" || Number(val) < 0 ? "text-red-400" : "text-zinc-300") : "text-zinc-300"
                      )}>
                        {formatted}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!active && <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">Enter symbols separated by commas to compare (max 6).</div>}
    </div>
  );
}
