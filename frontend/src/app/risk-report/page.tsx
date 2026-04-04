"use client";

import { useQuery } from "@tanstack/react-query";
import { ShieldAlert, AlertTriangle } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface RiskReport {
  equity: number;
  cash: number;
  total_exposure: number;
  long_exposure: number;
  short_exposure: number;
  exposure_pct: number;
  cash_pct: number;
  unrealized_pl: number;
  position_count: number;
  positions: {
    symbol: string;
    market_value: number;
    pct_of_portfolio: number;
    unrealized_pl: number;
    unrealized_plpc: number;
  }[];
  error?: string;
}

export default function RiskReportPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["risk-report"],
    queryFn: () => apiFetch<RiskReport>("/risk-report"),
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <ShieldAlert className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Daily Risk Report</h1>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-20 bg-zinc-800" />
          ))}
        </div>
      ) : data ? (
        <>
          {data.error && (
            <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400">
              {data.error}
            </div>
          )}

          {/* Summary cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Card label="Equity" value={`$${data.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}`} />
            <Card label="Cash" value={`$${data.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}`} />
            <Card
              label="Total Exposure"
              value={`$${data.total_exposure.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
              alert={data.exposure_pct > 90}
            />
            <Card
              label="Exposure %"
              value={`${data.exposure_pct}%`}
              alert={data.exposure_pct > 90}
            />
            <Card label="Long Exposure" value={`$${data.long_exposure.toLocaleString(undefined, { minimumFractionDigits: 2 })}`} />
            <Card label="Short Exposure" value={`$${data.short_exposure.toLocaleString(undefined, { minimumFractionDigits: 2 })}`} />
            <Card
              label="Unrealized P&L"
              value={`${data.unrealized_pl >= 0 ? "+" : ""}$${data.unrealized_pl.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
              valueColor={data.unrealized_pl >= 0 ? "text-emerald-400" : "text-red-400"}
            />
            <Card label="Positions" value={String(data.position_count)} />
          </div>

          {/* Exposure bar */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <h3 className="mb-2 text-xs font-semibold text-zinc-400">Portfolio Allocation</h3>
            <div className="flex h-6 w-full overflow-hidden rounded-full bg-zinc-800">
              <div
                className="bg-cyan-600 transition-all"
                style={{ width: `${Math.min(data.exposure_pct, 100)}%` }}
                title={`Invested: ${data.exposure_pct}%`}
              />
              <div
                className="bg-zinc-600 transition-all"
                style={{ width: `${Math.max(data.cash_pct, 0)}%` }}
                title={`Cash: ${data.cash_pct}%`}
              />
            </div>
            <div className="mt-2 flex gap-4 text-xs text-zinc-500">
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-cyan-600" /> Invested {data.exposure_pct}%
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-zinc-600" /> Cash {data.cash_pct}%
              </span>
            </div>
          </div>

          {/* Risk warnings */}
          {(data.exposure_pct > 90 || data.position_count === 0) && (
            <div className="flex items-start gap-2 rounded-lg border border-yellow-800/50 bg-yellow-950/20 p-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-yellow-400" />
              <div className="text-sm text-yellow-300">
                {data.exposure_pct > 90 && (
                  <p>High portfolio exposure ({data.exposure_pct}%). Consider taking profits or reducing position sizes.</p>
                )}
                {data.position_count === 0 && (
                  <p>No open positions. Your portfolio is 100% cash.</p>
                )}
              </div>
            </div>
          )}

          {/* Position breakdown */}
          {data.positions.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 text-xs text-zinc-400">
                    <th className="px-3 py-2 text-left">Symbol</th>
                    <th className="px-3 py-2 text-right">Market Value</th>
                    <th className="px-3 py-2 text-right">% of Portfolio</th>
                    <th className="px-3 py-2 text-right">Unrealized P&L</th>
                    <th className="px-3 py-2 text-right">P&L %</th>
                    <th className="px-3 py-2 text-left">Concentration</th>
                  </tr>
                </thead>
                <tbody>
                  {data.positions.map((p) => (
                    <tr key={p.symbol} className="border-b border-zinc-800/50">
                      <td className="px-3 py-2 font-bold text-cyan-400">{p.symbol}</td>
                      <td className="px-3 py-2 text-right font-mono">
                        ${p.market_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{p.pct_of_portfolio}%</td>
                      <td className={cn("px-3 py-2 text-right font-mono", p.unrealized_pl >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {p.unrealized_pl >= 0 ? "+" : ""}${p.unrealized_pl.toFixed(2)}
                      </td>
                      <td className={cn("px-3 py-2 text-right font-mono", p.unrealized_plpc >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {p.unrealized_plpc >= 0 ? "+" : ""}{p.unrealized_plpc.toFixed(2)}%
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-20 rounded-full bg-zinc-800">
                            <div
                              className={cn("h-2 rounded-full", p.pct_of_portfolio > 20 ? "bg-yellow-500" : "bg-cyan-500")}
                              style={{ width: `${Math.min(p.pct_of_portfolio, 100)}%` }}
                            />
                          </div>
                          {p.pct_of_portfolio > 20 && (
                            <AlertTriangle className="h-3 w-3 text-yellow-400" />
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

function Card({
  label,
  value,
  alert,
  valueColor,
}: {
  label: string;
  value: string;
  alert?: boolean;
  valueColor?: string;
}) {
  return (
    <div className={cn("rounded-lg border bg-zinc-900/50 p-3", alert ? "border-yellow-700" : "border-zinc-800")}>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className={cn("text-lg font-bold font-mono", valueColor)}>{value}</p>
    </div>
  );
}
