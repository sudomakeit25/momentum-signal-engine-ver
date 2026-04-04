"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Wallet } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface Position {
  symbol: string;
  qty: number;
  avg_entry: number;
  current_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_plpc: number;
  side: string;
}

interface PortfolioData {
  equity: number;
  cash: number;
  buying_power: number;
  positions: Position[];
  error?: string;
}

function usePortfolio() {
  return useQuery({
    queryKey: ["portfolio"],
    queryFn: () => apiFetch<PortfolioData>("/portfolio"),
    refetchInterval: 30_000,
  });
}

function useTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { symbol: string; qty: number; side: string }) =>
      fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/trade?symbol=${params.symbol}&qty=${params.qty}&side=${params.side}`,
        { method: "POST" }
      ).then((r) => r.json()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio"] }),
  });
}

export default function PortfolioPage() {
  const { data, isLoading } = usePortfolio();
  const trade = useTrade();

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Wallet className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Portfolio</h1>
      </div>

      {isLoading && !data ? (
        <div className="grid grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 bg-zinc-800" />
          ))}
        </div>
      ) : data ? (
        <>
          {data.error && (
            <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400">
              {data.error}
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <p className="text-xs text-zinc-500">Equity</p>
              <p className="text-2xl font-bold font-mono">${data.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <p className="text-xs text-zinc-500">Cash</p>
              <p className="text-2xl font-bold font-mono">${data.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <p className="text-xs text-zinc-500">Buying Power</p>
              <p className="text-2xl font-bold font-mono">${data.buying_power.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
            </div>
          </div>

          {data.positions.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 text-xs text-zinc-400">
                    <th className="px-4 py-3 text-left">Symbol</th>
                    <th className="px-4 py-3 text-right">Qty</th>
                    <th className="px-4 py-3 text-right">Avg Entry</th>
                    <th className="px-4 py-3 text-right">Current</th>
                    <th className="px-4 py-3 text-right">Market Value</th>
                    <th className="px-4 py-3 text-right">P&L</th>
                    <th className="px-4 py-3 text-right">P&L %</th>
                    <th className="px-4 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {data.positions.map((p) => (
                    <tr key={p.symbol} className="border-b border-zinc-800/50">
                      <td className="px-4 py-3 font-bold text-cyan-400">{p.symbol}</td>
                      <td className="px-4 py-3 text-right font-mono">{p.qty}</td>
                      <td className="px-4 py-3 text-right font-mono">${p.avg_entry.toFixed(2)}</td>
                      <td className="px-4 py-3 text-right font-mono">${p.current_price.toFixed(2)}</td>
                      <td className="px-4 py-3 text-right font-mono">${p.market_value.toFixed(2)}</td>
                      <td className={cn("px-4 py-3 text-right font-mono font-bold", p.unrealized_pl >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {p.unrealized_pl >= 0 ? "+" : ""}${p.unrealized_pl.toFixed(2)}
                      </td>
                      <td className={cn("px-4 py-3 text-right font-mono", p.unrealized_pl >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {p.unrealized_plpc >= 0 ? "+" : ""}{p.unrealized_plpc.toFixed(2)}%
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-xs text-red-400 border-red-800 hover:bg-red-950"
                          onClick={() => trade.mutate({ symbol: p.symbol, qty: p.qty, side: "SELL" })}
                          disabled={trade.isPending}
                        >
                          Close
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
              No open positions. Buy stocks from the Scanner signals.
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
