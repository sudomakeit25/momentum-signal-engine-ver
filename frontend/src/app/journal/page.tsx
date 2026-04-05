"use client";

import { useState } from "react";
import { BookMarked, Plus, Download, X } from "lucide-react";
import Link from "next/link";
import {
  useTrades,
  useJournalStats,
  useAddTrade,
  useCloseTrade,
  useImportAlpaca,
} from "@/hooks/use-journal";
import type { Trade, JournalStats } from "@/hooks/use-journal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function StatCard({
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
      <p className={cn("text-xl font-bold", color || "text-zinc-200")}>
        {value}
      </p>
      <p className="text-xs text-zinc-500">{label}</p>
    </div>
  );
}

function TradeRow({
  trade,
  onClose,
}: {
  trade: Trade;
  onClose: (id: string) => void;
}) {
  const [exitPrice, setExitPrice] = useState("");
  const [showClose, setShowClose] = useState(false);

  return (
    <tr className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
      <td className="px-3 py-2">
        <Link
          href={`/chart/${trade.symbol}`}
          className="font-medium text-cyan-400 hover:underline"
        >
          {trade.symbol}
        </Link>
      </td>
      <td className="px-3 py-2 text-xs">
        <span
          className={
            trade.side === "buy" ? "text-emerald-400" : "text-red-400"
          }
        >
          {trade.side.toUpperCase()}
        </span>
      </td>
      <td className="px-3 py-2 font-mono text-xs">{trade.shares}</td>
      <td className="px-3 py-2 font-mono text-xs">${trade.entry_price.toFixed(2)}</td>
      <td className="px-3 py-2 font-mono text-xs">
        {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : "-"}
      </td>
      <td className="px-3 py-2">
        {trade.pnl !== null ? (
          <span
            className={cn(
              "font-mono text-xs",
              trade.pnl >= 0 ? "text-emerald-400" : "text-red-400"
            )}
          >
            {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
          </span>
        ) : (
          "-"
        )}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-zinc-400">
        {trade.r_multiple !== null ? `${trade.r_multiple}R` : "-"}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-500">{trade.setup_type || "-"}</td>
      <td className="px-3 py-2">
        {trade.status === "open" ? (
          showClose ? (
            <div className="flex items-center gap-1">
              <Input
                type="number"
                placeholder="Exit $"
                value={exitPrice}
                onChange={(e) => setExitPrice(e.target.value)}
                className="h-6 w-20 bg-zinc-900 text-xs"
              />
              <Button
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => {
                  if (exitPrice) onClose(trade.id);
                  setShowClose(false);
                }}
              >
                OK
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-6 px-1"
                onClick={() => setShowClose(false)}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-xs"
              onClick={() => setShowClose(true)}
            >
              Close
            </Button>
          )
        ) : (
          <span className="text-xs text-zinc-600">Closed</span>
        )}
      </td>
    </tr>
  );
}

export default function JournalPage() {
  const { data: trades, isLoading: tradesLoading } = useTrades();
  const { data: stats } = useJournalStats();
  const addTrade = useAddTrade();
  const closeTrade = useCloseTrade();
  const importAlpaca = useImportAlpaca();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    symbol: "",
    side: "buy",
    shares: "",
    entry_price: "",
    stop_loss: "",
    target: "",
    setup_type: "",
    notes: "",
  });

  function handleAdd() {
    addTrade.mutate({
      symbol: form.symbol,
      side: form.side,
      shares: Number(form.shares),
      entry_price: Number(form.entry_price),
      stop_loss: Number(form.stop_loss) || 0,
      target: Number(form.target) || 0,
      setup_type: form.setup_type,
      notes: form.notes,
    });
    setShowAdd(false);
    setForm({ symbol: "", side: "buy", shares: "", entry_price: "", stop_loss: "", target: "", setup_type: "", notes: "" });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <BookMarked className="h-5 w-5 text-cyan-400" />
          <h1 className="text-lg font-bold">Trade Journal</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowAdd(!showAdd)}
            className="gap-1 text-xs"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Trade
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => importAlpaca.mutate(30)}
            disabled={importAlpaca.isPending}
            className="gap-1 text-xs"
          >
            <Download className="h-3.5 w-3.5" />
            {importAlpaca.isPending ? "Importing..." : "Import Alpaca"}
          </Button>
        </div>
      </div>

      {/* Stats */}
      {stats && stats.closed_trades > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
          <StatCard label="Win Rate" value={`${stats.win_rate}%`} color={stats.win_rate >= 50 ? "text-emerald-400" : "text-red-400"} />
          <StatCard label="Total P&L" value={`$${stats.total_pnl.toLocaleString()}`} color={stats.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"} />
          <StatCard label="Avg R" value={`${stats.avg_r_multiple}R`} color={stats.avg_r_multiple >= 1 ? "text-emerald-400" : "text-zinc-300"} />
          <StatCard label="Expectancy" value={`$${stats.expectancy}`} color={stats.expectancy >= 0 ? "text-emerald-400" : "text-red-400"} />
          <StatCard label="Profit Factor" value={stats.profit_factor.toFixed(1)} />
          <StatCard label="Trades" value={stats.closed_trades} />
          <StatCard label="Open" value={stats.open_trades} />
        </div>
      )}

      {/* Add Trade Form */}
      {showAdd && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Symbol</Label>
              <Input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} className="h-8 bg-zinc-900" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Side</Label>
              <select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })} className="h-8 w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 text-sm">
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Shares</Label>
              <Input type="number" value={form.shares} onChange={(e) => setForm({ ...form, shares: e.target.value })} className="h-8 bg-zinc-900" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Entry Price</Label>
              <Input type="number" value={form.entry_price} onChange={(e) => setForm({ ...form, entry_price: e.target.value })} className="h-8 bg-zinc-900" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Stop Loss</Label>
              <Input type="number" value={form.stop_loss} onChange={(e) => setForm({ ...form, stop_loss: e.target.value })} className="h-8 bg-zinc-900" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Target</Label>
              <Input type="number" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} className="h-8 bg-zinc-900" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Setup Type</Label>
              <Input value={form.setup_type} onChange={(e) => setForm({ ...form, setup_type: e.target.value })} className="h-8 bg-zinc-900" placeholder="e.g. ema_crossover" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Notes</Label>
              <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="h-8 bg-zinc-900" />
            </div>
          </div>
          <Button size="sm" onClick={handleAdd} disabled={!form.symbol || !form.shares || !form.entry_price}>
            Save Trade
          </Button>
        </div>
      )}

      {/* Trades Table */}
      {tradesLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full bg-zinc-800" />
          ))}
        </div>
      ) : trades && trades.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                <th className="px-3 py-2 font-medium">Symbol</th>
                <th className="px-3 py-2 font-medium">Side</th>
                <th className="px-3 py-2 font-medium">Shares</th>
                <th className="px-3 py-2 font-medium">Entry</th>
                <th className="px-3 py-2 font-medium">Exit</th>
                <th className="px-3 py-2 font-medium">P&L</th>
                <th className="px-3 py-2 font-medium">R</th>
                <th className="px-3 py-2 font-medium">Setup</th>
                <th className="px-3 py-2 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <TradeRow
                  key={trade.id}
                  trade={trade}
                  onClose={(id) =>
                    closeTrade.mutate({ tradeId: id, exitPrice: 0 })
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          No trades yet. Add one manually or import from Alpaca.
        </div>
      )}

      {/* Setup Breakdown */}
      {stats && stats.by_setup && Object.keys(stats.by_setup).length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-zinc-300">Performance by Setup</h2>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {Object.entries(stats.by_setup).map(([setup, data]) => (
              <div key={setup} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
                <p className="text-xs font-medium text-cyan-400">{setup}</p>
                <div className="mt-1 flex items-center gap-3 text-xs">
                  <span className={data.win_rate >= 50 ? "text-emerald-400" : "text-red-400"}>
                    {data.win_rate}% WR
                  </span>
                  <span className="text-zinc-500">{data.trades} trades</span>
                  <span className={data.pnl >= 0 ? "text-emerald-400" : "text-red-400"}>
                    ${data.pnl}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
