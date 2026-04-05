"use client";

import { useState } from "react";
import { BarChart3 } from "lucide-react";
import Link from "next/link";
import { useSignalBacktest } from "@/hooks/use-journal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function StatBox({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
      <p className={cn("text-lg font-bold", color || "text-zinc-200")}>
        {value}
      </p>
      <p className="text-[10px] text-zinc-500">{label}</p>
    </div>
  );
}

export default function SignalBacktestPage() {
  const [symbol, setSymbol] = useState("");
  const [activeSymbol, setActiveSymbol] = useState("");
  const [days, setDays] = useState(200);
  const [lookforward, setLookforward] = useState(10);

  const { data, isLoading } = useSignalBacktest(
    activeSymbol,
    days,
    lookforward
  );

  const stats = data?.stats as Record<string, unknown> | undefined;
  const signals = (data?.signals as Record<string, unknown>[]) || [];
  const bySetup = (stats?.by_setup as Record<string, { total: number; wins: number; win_rate: number; avg_pnl: number }>) || {};

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <BarChart3 className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Signal Backtester</h1>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
        Tests how actual generated signals would have performed historically.
        For each signal, checks if the target or stop loss was hit within the
        lookforward window.
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Symbol</label>
          <Input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && setActiveSymbol(symbol)}
            placeholder="AAPL"
            className="h-8 w-28 bg-zinc-900"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Days</label>
          <Input
            type="number"
            value={days}
            onChange={(e) => setDays(Number(e.target.value) || 200)}
            className="h-8 w-20 bg-zinc-900"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Lookforward</label>
          <Input
            type="number"
            value={lookforward}
            onChange={(e) => setLookforward(Number(e.target.value) || 10)}
            className="h-8 w-20 bg-zinc-900"
          />
        </div>
        <Button
          size="sm"
          onClick={() => setActiveSymbol(symbol)}
          disabled={!symbol || isLoading}
        >
          {isLoading ? "Running..." : "Backtest"}
        </Button>
      </div>

      {isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full bg-zinc-800" />
          <Skeleton className="h-40 w-full bg-zinc-800" />
        </div>
      )}

      {stats && !isLoading && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
            <StatBox
              label="Win Rate"
              value={`${stats.win_rate}%`}
              color={
                (stats.win_rate as number) >= 50
                  ? "text-emerald-400"
                  : "text-red-400"
              }
            />
            <StatBox label="Total Signals" value={stats.total_signals as number} />
            <StatBox
              label="Wins"
              value={stats.wins as number}
              color="text-emerald-400"
            />
            <StatBox
              label="Losses"
              value={stats.losses as number}
              color="text-red-400"
            />
            <StatBox label="Expired" value={stats.expired as number} />
            <StatBox
              label="Avg P&L %"
              value={`${stats.avg_pnl_pct}%`}
              color={
                (stats.avg_pnl_pct as number) >= 0
                  ? "text-emerald-400"
                  : "text-red-400"
              }
            />
            <StatBox
              label="Avg R"
              value={`${stats.avg_r_multiple}R`}
              color={
                (stats.avg_r_multiple as number) >= 0
                  ? "text-emerald-400"
                  : "text-red-400"
              }
            />
          </div>

          {/* By Setup */}
          {Object.keys(bySetup).length > 0 && (
            <div className="space-y-2">
              <h2 className="text-sm font-medium text-zinc-300">
                By Setup Type
              </h2>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {Object.entries(bySetup).map(([setup, d]) => (
                  <div
                    key={setup}
                    className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3"
                  >
                    <p className="text-xs font-medium text-cyan-400">
                      {setup}
                    </p>
                    <div className="mt-1 flex gap-3 text-xs">
                      <span
                        className={
                          d.win_rate >= 50
                            ? "text-emerald-400"
                            : "text-red-400"
                        }
                      >
                        {d.win_rate}%
                      </span>
                      <span className="text-zinc-500">{d.total} signals</span>
                      <span
                        className={
                          d.avg_pnl >= 0
                            ? "text-emerald-400"
                            : "text-red-400"
                        }
                      >
                        {d.avg_pnl}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent Signals */}
          {signals.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-sm font-medium text-zinc-300">
                Recent Signals ({signals.length})
              </h2>
              <div className="overflow-x-auto rounded-lg border border-zinc-800">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-zinc-400">
                      <th className="px-3 py-2 font-medium">Date</th>
                      <th className="px-3 py-2 font-medium">Action</th>
                      <th className="px-3 py-2 font-medium">Setup</th>
                      <th className="px-3 py-2 font-medium text-right">
                        Entry
                      </th>
                      <th className="px-3 py-2 font-medium">Outcome</th>
                      <th className="px-3 py-2 font-medium text-right">
                        P&L %
                      </th>
                      <th className="px-3 py-2 font-medium text-right">R</th>
                      <th className="px-3 py-2 font-medium text-right">
                        Bars
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {signals.map((s, i) => (
                      <tr
                        key={i}
                        className="border-b border-zinc-800/30 hover:bg-zinc-800/20"
                      >
                        <td className="px-3 py-1.5 text-zinc-500">
                          {(s.date as string).slice(0, 10)}
                        </td>
                        <td className="px-3 py-1.5">
                          <span
                            className={
                              s.action === "BUY"
                                ? "text-emerald-400"
                                : "text-red-400"
                            }
                          >
                            {s.action as string}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-zinc-400">
                          {s.setup_type as string}
                        </td>
                        <td className="px-3 py-1.5 text-right font-mono text-zinc-300">
                          ${(s.entry as number).toFixed(2)}
                        </td>
                        <td className="px-3 py-1.5">
                          <span
                            className={cn(
                              "font-medium",
                              s.outcome === "win"
                                ? "text-emerald-400"
                                : s.outcome === "loss"
                                  ? "text-red-400"
                                  : "text-zinc-500"
                            )}
                          >
                            {(s.outcome as string).toUpperCase()}
                          </span>
                        </td>
                        <td
                          className={cn(
                            "px-3 py-1.5 text-right font-mono",
                            (s.pnl_pct as number) >= 0
                              ? "text-emerald-400"
                              : "text-red-400"
                          )}
                        >
                          {(s.pnl_pct as number) >= 0 ? "+" : ""}
                          {s.pnl_pct}%
                        </td>
                        <td className="px-3 py-1.5 text-right font-mono text-zinc-400">
                          {s.r_multiple}R
                        </td>
                        <td className="px-3 py-1.5 text-right text-zinc-500">
                          {s.bars_to_exit as number}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {!activeSymbol && !isLoading && (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          Enter a symbol and click Backtest to see how generated signals
          performed historically.
        </div>
      )}
    </div>
  );
}
