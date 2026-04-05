"use client";

import { useState } from "react";
import { Wrench } from "lucide-react";
import { useOptionsStrategies, useOptionsStrategy } from "@/hooks/use-trading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function OptionsBuilderPage() {
  const [price, setPrice] = useState("");
  const [selectedStrategy, setSelectedStrategy] = useState("");
  const { data: strategies } = useOptionsStrategies();
  const { data: result, isLoading } = useOptionsStrategy(selectedStrategy, Number(price));

  const legs = (result?.legs as Record<string, unknown>[]) || [];
  const pnlData = (result?.pnl_data as { price: number; pnl: number }[]) || [];
  const breakevens = (result?.breakevens as number[]) || [];

  // Find min/max P&L for chart scaling
  const maxPnl = Math.max(...pnlData.map((d) => d.pnl), 0);
  const minPnl = Math.min(...pnlData.map((d) => d.pnl), 0);
  const range = maxPnl - minPnl || 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Wrench className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Options Strategy Builder</h1>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label className="text-xs text-zinc-400">Stock Price</Label>
            <Input type="number" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="e.g. 150" className="h-8 w-28 bg-zinc-900" />
          </div>
        </div>
        {strategies && (
          <div className="flex flex-wrap gap-1.5">
            {(strategies as Record<string, unknown>[]).map((s) => (
              <Button
                key={String(s.key)}
                size="sm"
                variant={selectedStrategy === String(s.key) ? "default" : "outline"}
                className="h-7 px-2 text-[11px]"
                onClick={() => setSelectedStrategy(String(s.key))}
                disabled={!price}
              >
                {String(s.name)}
              </Button>
            ))}
          </div>
        )}
      </div>

      {isLoading && <Skeleton className="h-60 w-full bg-zinc-800" />}

      {result && !isLoading && (
        <div className="space-y-4">
          {/* Strategy Summary */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <h2 className="text-sm font-bold text-cyan-400">{String(result.strategy)}</h2>
            <p className="text-xs text-zinc-500">{String(result.description)}</p>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="text-center"><p className="text-lg font-bold text-emerald-400">${String(result.max_profit)}</p><p className="text-[10px] text-zinc-500">Max Profit</p></div>
              <div className="text-center"><p className="text-lg font-bold text-red-400">${String(result.max_loss)}</p><p className="text-[10px] text-zinc-500">Max Loss</p></div>
              <div className="text-center"><p className="text-lg font-bold text-zinc-300">${String(result.net_premium)}</p><p className="text-[10px] text-zinc-500">Net Premium</p></div>
              <div className="text-center"><p className="text-lg font-bold text-zinc-300">{breakevens.map((b) => `$${b}`).join(", ") || "-"}</p><p className="text-[10px] text-zinc-500">Breakeven</p></div>
            </div>
          </div>

          {/* Legs */}
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400"><th className="px-3 py-2">Type</th><th className="px-3 py-2">Side</th><th className="px-3 py-2 text-right">Strike</th><th className="px-3 py-2 text-right">Premium</th></tr></thead>
              <tbody>{legs.map((l, i) => (
                <tr key={i} className="border-b border-zinc-800/50">
                  <td className={cn("px-3 py-2 font-medium", String(l.type) === "call" ? "text-emerald-400" : "text-red-400")}>{String(l.type).toUpperCase()}</td>
                  <td className="px-3 py-2 text-zinc-300">{String(l.side).toUpperCase()}</td>
                  <td className="px-3 py-2 text-right font-mono">${Number(l.strike).toFixed(2)}</td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-400">${Number(l.premium).toFixed(2)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>

          {/* P&L Chart (ASCII-style bar chart) */}
          {pnlData.length > 0 && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <h3 className="text-xs font-medium text-zinc-400 mb-2">P&L at Expiration</h3>
              <div className="flex items-end gap-px h-40">
                {pnlData.filter((_, i) => i % 2 === 0).map((d, i) => {
                  const height = Math.abs(d.pnl) / range * 100;
                  const isProfit = d.pnl >= 0;
                  return (
                    <div key={i} className="flex-1 flex flex-col justify-end items-center" title={`$${d.price}: ${d.pnl >= 0 ? "+" : ""}$${d.pnl}`}>
                      <div
                        className={cn("w-full rounded-t-sm min-h-[1px]", isProfit ? "bg-emerald-400/60" : "bg-red-400/60")}
                        style={{ height: `${Math.max(height, 1)}%` }}
                      />
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-between text-[10px] text-zinc-600 mt-1">
                <span>${pnlData[0]?.price}</span>
                <span>${Number(price).toFixed(0)} (current)</span>
                <span>${pnlData[pnlData.length - 1]?.price}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {!selectedStrategy && !isLoading && <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">Enter a stock price and select a strategy to see P&L analysis.</div>}
    </div>
  );
}
