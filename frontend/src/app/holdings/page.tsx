"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Briefcase } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { apiPostJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type PortfolioHolding = {
  symbol: string;
  sector: string;
  price: number;
  shares: number;
  value: number;
  weight: number;
  ret_1y_pct: number | null;
};

type PortfolioResult = {
  error?: string;
  total_value: number;
  holdings: PortfolioHolding[];
  sector_weights: Record<string, number>;
  correlation: { symbols: string[]; matrix: number[][] };
  portfolio: {
    beta_vs_spy: number | null;
    annualized_vol_pct: number | null;
    max_drawdown_pct: number | null;
    return_1y_pct: number | null;
  };
};

const SECTOR_COLORS = [
  "#06b6d4", "#f59e0b", "#10b981", "#ec4899", "#8b5cf6",
  "#ef4444", "#84cc16", "#3b82f6", "#f97316", "#a855f7",
];

function fmtMoney(n: number) {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

function corrColor(v: number): string {
  // Red for 1.0 (perfectly correlated), blue for -1.0, neutral near 0
  const t = Math.max(-1, Math.min(1, v));
  if (t > 0) {
    return `rgba(239, 68, 68, ${0.15 + t * 0.5})`;
  }
  return `rgba(59, 130, 246, ${0.15 - t * 0.5})`;
}

export default function HoldingsPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<PortfolioResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function parseAndAnalyze() {
    setError("");
    setLoading(true);
    setResult(null);
    try {
      const parsed = await apiPostJson<{ holdings: { symbol: string; shares?: number }[] }>(
        "/portfolio/parse",
        { text },
      );
      if (parsed.holdings.length === 0) {
        setError("No tickers recognized in pasted text.");
        return;
      }
      const analyzed = await apiPostJson<PortfolioResult>("/portfolio/analyze", {
        holdings: parsed.holdings,
      });
      setResult(analyzed);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const pieData = useMemo(() => {
    if (!result) return [];
    return Object.entries(result.sector_weights).map(([sector, weight], i) => ({
      sector,
      weight: Math.round(weight * 10000) / 100,
      color: SECTOR_COLORS[i % SECTOR_COLORS.length],
    }));
  }, [result]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Briefcase className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">My Holdings</h1>
      </div>

      <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
        <label className="text-xs text-zinc-400">
          Paste your portfolio (Robinhood, CSV, or one symbol per line). Shares
          optional - with shares we compute weights, beta, and drawdowns.
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"RKLB\n10,400 shares\n$85.48\nMU\n900 shares\n$459.30"}
          className="h-40 w-full rounded-md border border-zinc-700 bg-zinc-900 p-2 text-xs font-mono"
        />
        <Button size="sm" onClick={parseAndAnalyze} disabled={loading || !text.trim()}>
          {loading ? "Analyzing..." : "Parse & Analyze"}
        </Button>
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>

      {loading && !result && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full bg-zinc-800" />
          ))}
        </div>
      )}

      {result && result.error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">
          {result.error}
        </div>
      )}

      {result && !result.error && (
        <>
          {/* Aggregate stats */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <StatCard label="Total Value" value={fmtMoney(result.total_value)} />
            <StatCard
              label="1Y Return"
              value={fmtPct(result.portfolio.return_1y_pct)}
              color={pctColor(result.portfolio.return_1y_pct)}
            />
            <StatCard
              label="Beta vs SPY"
              value={result.portfolio.beta_vs_spy?.toFixed(2) ?? "-"}
              color={
                result.portfolio.beta_vs_spy && result.portfolio.beta_vs_spy > 1.3
                  ? "text-amber-400"
                  : undefined
              }
            />
            <StatCard
              label="Annualized Vol"
              value={fmtPct(result.portfolio.annualized_vol_pct)}
              color="text-amber-400"
            />
            <StatCard
              label="Max Drawdown"
              value={fmtPct(result.portfolio.max_drawdown_pct)}
              color="text-red-400"
            />
          </div>

          {/* Sector pie + holdings table side-by-side on wide screens */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
                Sector Concentration
              </div>
              {pieData.length > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie
                        data={pieData}
                        dataKey="weight"
                        nameKey="sector"
                        outerRadius={80}
                        innerRadius={35}
                        strokeWidth={1}
                        stroke="#18181b"
                      >
                        {pieData.map((d, i) => (
                          <Cell key={i} fill={d.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
                        formatter={(v) => `${Number(v).toFixed(1)}%`}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="mt-1 space-y-1 text-xs">
                    {pieData.map((d) => (
                      <div key={d.sector} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2">
                          <span
                            className="h-2 w-2 rounded-full"
                            style={{ background: d.color }}
                          />
                          <span className="text-zinc-300">{d.sector}</span>
                        </span>
                        <span className="font-mono text-zinc-400">
                          {d.weight.toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-xs text-zinc-500">No sector data.</p>
              )}
            </div>

            <div className="lg:col-span-2 overflow-x-auto rounded-lg border border-zinc-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                    <th className="px-3 py-2">Symbol</th>
                    <th className="px-3 py-2">Sector</th>
                    <th className="px-3 py-2 text-right">Shares</th>
                    <th className="px-3 py-2 text-right">Price</th>
                    <th className="px-3 py-2 text-right">Value</th>
                    <th className="px-3 py-2 text-right">Weight</th>
                    <th className="px-3 py-2 text-right">1Y</th>
                  </tr>
                </thead>
                <tbody>
                  {[...result.holdings]
                    .sort((a, b) => b.value - a.value)
                    .map((h) => (
                      <tr key={h.symbol} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                        <td className="px-3 py-2">
                          <Link href={`/analyzer`} className="text-cyan-400 hover:underline">
                            {h.symbol}
                          </Link>
                        </td>
                        <td className="px-3 py-2 text-xs text-zinc-400">{h.sector}</td>
                        <td className="px-3 py-2 text-right font-mono text-zinc-400">
                          {h.shares ? h.shares.toLocaleString() : "-"}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {h.price ? `$${h.price.toFixed(2)}` : "-"}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {h.value ? fmtMoney(h.value) : "-"}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {(h.weight * 100).toFixed(1)}%
                        </td>
                        <td className={cn(
                          "px-3 py-2 text-right font-mono",
                          pctColor(h.ret_1y_pct),
                        )}>
                          {fmtPct(h.ret_1y_pct)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Correlation matrix */}
          {result.correlation.symbols.length >= 2 && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
                Correlation Matrix (daily returns, ~1y)
              </div>
              <div className="overflow-x-auto">
                <table className="text-xs font-mono">
                  <thead>
                    <tr>
                      <th className="p-2"></th>
                      {result.correlation.symbols.map((s) => (
                        <th key={s} className="px-2 py-1 text-zinc-400">{s}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.correlation.symbols.map((rowSym, i) => (
                      <tr key={rowSym}>
                        <td className="px-2 py-1 text-right text-zinc-400">{rowSym}</td>
                        {result.correlation.matrix[i].map((v, j) => (
                          <td
                            key={j}
                            className="px-2 py-1 text-center text-zinc-100"
                            style={{ background: corrColor(v), minWidth: 42 }}
                            title={`${rowSym} ↔ ${result.correlation.symbols[j]}: ${v.toFixed(3)}`}
                          >
                            {v.toFixed(2)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[10px] text-zinc-500">
                Red cells = high positive correlation (low diversification benefit). Blue = negative correlation.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="text-[10px] uppercase text-zinc-500">{label}</div>
      <div className={cn("mt-1 font-mono text-lg", color)}>{value}</div>
    </div>
  );
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

function pctColor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-zinc-500";
  return v >= 0 ? "text-emerald-400" : "text-red-400";
}
