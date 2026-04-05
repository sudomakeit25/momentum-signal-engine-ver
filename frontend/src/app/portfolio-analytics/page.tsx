"use client";

import { PieChart } from "lucide-react";
import Link from "next/link";
import { usePortfolioAnalytics } from "@/hooks/use-advanced";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function Stat({ label, value, color, sub }: { label: string; value: string | number; color?: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
      <p className={cn("text-lg font-bold", color || "text-zinc-200")}>{value}</p>
      <p className="text-[10px] text-zinc-500">{label}</p>
      {sub && <p className="text-[10px] text-zinc-600">{sub}</p>}
    </div>
  );
}

export default function PortfolioAnalyticsPage() {
  const { data, isLoading } = usePortfolioAnalytics();

  if (isLoading) return <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 bg-zinc-800" />)}</div>;
  if (!data || data.error) return <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">{String(data?.error || "No portfolio data. Open positions in Paper Trading first.")}</div>;

  const acct = data.account as Record<string, unknown>;
  const heatMap = (data.heat_map || []) as Record<string, unknown>[];
  const dd = (data.drawdown || {}) as Record<string, unknown>;
  const sharpe = (data.sharpe || {}) as Record<string, unknown>;
  const beta = (data.beta || {}) as Record<string, unknown>;
  const conc = (data.concentration || {}) as Record<string, unknown>;
  const cashAlloc = (data.cash_allocation || {}) as Record<string, unknown>;
  const margin = (data.margin || {}) as Record<string, unknown>;
  const rebal = (data.rebalancing || {}) as Record<string, unknown>;
  const income = (data.income || {}) as Record<string, unknown>;
  const hasHeatMap = Array.isArray(heatMap) && heatMap.length > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <PieChart className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Portfolio Analytics</h1>
      </div>

      {/* Account Overview */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Stat label="Equity" value={`$${Number(acct.equity).toLocaleString()}`} />
        <Stat label="Cash" value={`$${Number(acct.cash).toLocaleString()}`} />
        <Stat label="Invested" value={`$${Number(acct.invested).toLocaleString()}`} />
        <Stat label="P&L" value={`$${Number(acct.total_unrealized_pnl).toLocaleString()}`} color={Number(acct.total_unrealized_pnl) >= 0 ? "text-emerald-400" : "text-red-400"} />
        <Stat label="P&L %" value={`${acct.total_pnl_pct}%`} color={Number(acct.total_pnl_pct) >= 0 ? "text-emerald-400" : "text-red-400"} />
      </div>

      {/* Risk Metrics */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Sharpe Ratio" value={String(sharpe?.ratio)} sub={String(sharpe?.interpretation)} />
        <Stat label="Portfolio Beta" value={String(beta?.portfolio_beta)} sub={String(beta?.interpretation)} />
        <Stat label="Drawdown" value={`${dd?.current_drawdown_pct}%`} color={Number(dd?.current_drawdown_pct) < -5 ? "text-red-400" : "text-zinc-300"} sub={String(dd?.status)} />
        <Stat label="Cash %" value={`${cashAlloc?.cash_pct}%`} sub={String(cashAlloc?.recommendation).slice(0, 40)} />
      </div>

      {/* Heat Map */}
      {hasHeatMap && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-zinc-300">Sector Heat Map</h2>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {heatMap.map((s, i) => (
              <div key={i} className={cn("rounded-lg border p-3", Number(s.pnl) >= 0 ? "border-emerald-800/30 bg-emerald-900/10" : "border-red-800/30 bg-red-900/10")}>
                <p className="text-xs font-medium text-zinc-300">{String(s.sector)}</p>
                <p className={cn("text-sm font-bold", Number(s.pnl) >= 0 ? "text-emerald-400" : "text-red-400")}>${Number(s.value).toLocaleString()}</p>
                <p className={cn("text-xs", Number(s.pnl) >= 0 ? "text-emerald-400/70" : "text-red-400/70")}>{Number(s.pnl) >= 0 ? "+" : ""}${Number(s.pnl).toFixed(0)}</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {((s.stocks as Record<string, unknown>[]) || []).map((st, j) => (
                    <Link key={j} href={`/chart/${st.symbol}`} className="text-[10px] text-cyan-400 hover:underline">{String(st.symbol)}</Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Concentration Alerts */}
      {Array.isArray(conc?.alerts) && (conc.alerts as unknown[]).length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-zinc-300">Concentration Alerts</h2>
          {((conc!.alerts as Record<string, unknown>[]) || []).map((a, i) => (
            <div key={i} className="rounded-lg border border-amber-800/30 bg-amber-900/10 p-3 text-xs text-amber-400">{String(a.message)}</div>
          ))}
        </div>
      )}

      {/* Rebalancing */}
      {Boolean(rebal?.needs_rebalancing) && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-zinc-300">Rebalancing Needed</h2>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-zinc-800 bg-zinc-900/50 text-zinc-400"><th className="px-3 py-2 text-left">Symbol</th><th className="px-3 py-2 text-right">Actual</th><th className="px-3 py-2 text-right">Target</th><th className="px-3 py-2 text-right">Drift</th><th className="px-3 py-2">Action</th></tr></thead>
              <tbody>{((rebal!.drift_alerts as Record<string, unknown>[]) || []).map((d, i) => (
                <tr key={i} className="border-b border-zinc-800/30"><td className="px-3 py-1.5 text-cyan-400">{String(d.symbol)}</td><td className="px-3 py-1.5 text-right font-mono">{String(d.actual_pct)}%</td><td className="px-3 py-1.5 text-right font-mono text-zinc-500">{String(d.target_pct)}%</td><td className={cn("px-3 py-1.5 text-right font-mono", Number(d.drift) > 0 ? "text-amber-400" : "text-cyan-400")}>{Number(d.drift) > 0 ? "+" : ""}{String(d.drift)}%</td><td className="px-3 py-1.5">{String(d.action)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}

      {/* Income */}
      {Number(income?.est_annual_income) > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-zinc-300">Estimated Income</h2>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Annual" value={`$${Number(income.est_annual_income).toFixed(0)}`} color="text-emerald-400" />
            <Stat label="Monthly" value={`$${Number(income.est_monthly_income).toFixed(0)}`} color="text-emerald-400" />
          </div>
        </div>
      )}

      {/* Margin */}
      {Number(margin?.margin_used_pct) > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs">
          <span className="text-zinc-500">Margin: </span>
          <span className={cn("font-mono", margin.status === "high" ? "text-red-400" : "text-zinc-300")}>{String(margin.margin_used_pct)}% used</span>
          <span className="text-zinc-600"> (${Number(margin.margin_used).toLocaleString()} of ${Number(margin.margin_available).toLocaleString()} available)</span>
        </div>
      )}
    </div>
  );
}
