"use client";

import { useState } from "react";
import { BarChart3 } from "lucide-react";
import { useBacktest } from "@/hooks/use-backtest";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { BacktestTrade } from "@/types/api";

function formatDate(iso: string): string {
  return iso.split("T")[0];
}

function computeEquityCurve(trades: BacktestTrade[], capital: number) {
  let equity = capital;
  const points = [{ date: trades[0]?.entry_date?.split("T")[0] || "", value: equity }];
  for (const t of trades) {
    equity += t.pnl;
    points.push({ date: formatDate(t.exit_date), value: Math.round(equity) });
  }
  return points;
}

function computeDrawdown(trades: BacktestTrade[], capital: number) {
  let equity = capital;
  let peak = capital;
  const points: { date: string; drawdown: number }[] = [];
  for (const t of trades) {
    equity += t.pnl;
    peak = Math.max(peak, equity);
    const dd = ((peak - equity) / peak) * -100;
    points.push({ date: formatDate(t.exit_date), drawdown: Math.round(dd * 100) / 100 });
  }
  return points;
}

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("SPY");
  const [days, setDays] = useState(365);
  const [capital, setCapital] = useState(100000);
  const [riskPct, setRiskPct] = useState(2);
  const [enabled, setEnabled] = useState(false);
  const [page, setPage] = useState(0);
  const perPage = 10;

  const { data, isLoading } = useBacktest(
    { symbol, days, capital, risk_pct: riskPct },
    enabled
  );

  const handleRun = () => {
    setEnabled(true);
    setPage(0);
  };

  const equityCurve = data?.trades.length ? computeEquityCurve(data.trades, capital) : [];
  const drawdownData = data?.trades.length ? computeDrawdown(data.trades, capital) : [];

  const pageStart = page * perPage;
  const pageTrades = data?.trades.slice(pageStart, pageStart + perPage) || [];
  const totalPages = data ? Math.ceil(data.trades.length / perPage) : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <BarChart3 className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Backtest</h1>
      </div>

      {/* Form */}
      <div className="flex flex-wrap items-end gap-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="space-y-1">
          <Label className="text-xs text-zinc-400">Symbol</Label>
          <Input
            value={symbol}
            onChange={(e) => { setSymbol(e.target.value.toUpperCase()); setEnabled(false); }}
            className="h-8 w-24 bg-zinc-900"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-zinc-400">Days</Label>
          <Input
            type="number"
            value={days}
            onChange={(e) => { setDays(Number(e.target.value)); setEnabled(false); }}
            className="h-8 w-20 bg-zinc-900"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-zinc-400">Capital ($)</Label>
          <Input
            type="number"
            value={capital}
            onChange={(e) => { setCapital(Number(e.target.value)); setEnabled(false); }}
            className="h-8 w-28 bg-zinc-900"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-zinc-400">Risk %</Label>
          <Input
            type="number"
            step="0.5"
            value={riskPct}
            onChange={(e) => { setRiskPct(Number(e.target.value)); setEnabled(false); }}
            className="h-8 w-20 bg-zinc-900"
          />
        </div>
        <Button onClick={handleRun} disabled={isLoading} className="h-8 bg-cyan-600 hover:bg-cyan-700">
          {isLoading ? "Running..." : "Run Backtest"}
        </Button>
      </div>

      {isLoading && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-20 bg-zinc-800" />
            ))}
          </div>
          <Skeleton className="h-48 bg-zinc-800" />
        </div>
      )}

      {data && !isLoading && (
        <>
          {/* Stats Cards */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <StatCard label="Total Trades" value={data.total_trades.toString()} />
            <StatCard
              label="Win Rate"
              value={`${(data.win_rate * 100).toFixed(1)}%`}
              color={data.win_rate >= 0.5 ? "text-emerald-400" : "text-red-400"}
            />
            <StatCard label="Avg R:R" value={data.avg_rr.toFixed(2)} />
            <StatCard
              label="Total Return"
              value={`${data.total_return_pct >= 0 ? "+" : ""}${data.total_return_pct.toFixed(2)}%`}
              color={data.total_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}
            />
            <StatCard
              label="Max Drawdown"
              value={`${data.max_drawdown_pct.toFixed(2)}%`}
              color="text-red-400"
            />
            <StatCard
              label="Period"
              value={`${formatDate(data.start_date)} - ${formatDate(data.end_date)}`}
              small
            />
          </div>

          {/* Equity Curve */}
          {equityCurve.length > 1 && (
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader>
                <CardTitle className="text-sm text-zinc-300">Equity Curve</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={equityCurve}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} />
                    <YAxis tick={{ fill: "#71717a", fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }}
                      labelStyle={{ color: "#a1a1aa" }}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="#22c55e"
                      fill="#22c55e20"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Drawdown Chart */}
          {drawdownData.length > 0 && (
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader>
                <CardTitle className="text-sm text-zinc-300">Drawdown</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={120}>
                  <AreaChart data={drawdownData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} />
                    <YAxis tick={{ fill: "#71717a", fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }}
                    />
                    <Area
                      type="monotone"
                      dataKey="drawdown"
                      stroke="#ef4444"
                      fill="#ef444420"
                      strokeWidth={1}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Trade Log */}
          {data.trades.length > 0 && (
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-sm text-zinc-300">
                  Trade Log ({data.trades.length} trades)
                </CardTitle>
                {totalPages > 1 && (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 text-xs"
                      disabled={page === 0}
                      onClick={() => setPage(page - 1)}
                    >
                      Prev
                    </Button>
                    <span className="text-xs text-zinc-500">
                      {page + 1} / {totalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 text-xs"
                      disabled={page >= totalPages - 1}
                      onClick={() => setPage(page + 1)}
                    >
                      Next
                    </Button>
                  </div>
                )}
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow className="border-zinc-800">
                      <TableHead className="text-zinc-400">#</TableHead>
                      <TableHead className="text-zinc-400">Entry</TableHead>
                      <TableHead className="text-zinc-400">Exit</TableHead>
                      <TableHead className="text-right text-zinc-400">Entry $</TableHead>
                      <TableHead className="text-right text-zinc-400">Exit $</TableHead>
                      <TableHead className="text-right text-zinc-400">Shares</TableHead>
                      <TableHead className="text-right text-zinc-400">P&L</TableHead>
                      <TableHead className="text-right text-zinc-400">Return</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pageTrades.map((t, i) => (
                      <TableRow key={i} className="border-zinc-800">
                        <TableCell className="font-mono text-xs text-zinc-500">
                          {pageStart + i + 1}
                        </TableCell>
                        <TableCell className="text-xs">{formatDate(t.entry_date)}</TableCell>
                        <TableCell className="text-xs">{formatDate(t.exit_date)}</TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          ${t.entry_price.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          ${t.exit_price.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {t.shares}
                        </TableCell>
                        <TableCell
                          className={`text-right font-mono text-xs ${
                            t.pnl >= 0 ? "text-emerald-400" : "text-red-400"
                          }`}
                        >
                          ${t.pnl.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                        </TableCell>
                        <TableCell
                          className={`text-right font-mono text-xs ${
                            t.return_pct >= 0 ? "text-emerald-400" : "text-red-400"
                          }`}
                        >
                          {t.return_pct >= 0 ? "+" : ""}
                          {t.return_pct.toFixed(2)}%
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {!data && !isLoading && (
        <div className="flex h-48 items-center justify-center rounded-lg border border-zinc-800 text-zinc-500">
          Configure parameters and click Run Backtest
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color = "text-zinc-100",
  small = false,
}: {
  label: string;
  value: string;
  color?: string;
  small?: boolean;
}) {
  return (
    <Card className="border-zinc-800 bg-zinc-900/50">
      <CardContent className="p-4">
        <div className="text-xs text-zinc-500">{label}</div>
        <div className={`${small ? "text-sm" : "text-xl"} font-bold ${color}`}>
          {value}
        </div>
      </CardContent>
    </Card>
  );
}
