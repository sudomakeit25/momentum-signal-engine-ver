"use client";

import { useState } from "react";
import { DollarSign } from "lucide-react";
import Link from "next/link";
import { useTradingAccount, useTradingPositions, useTradingOrders, usePlaceOrder, useClosePosition } from "@/hooks/use-trading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function TradingPage() {
  const { data: account } = useTradingAccount();
  const { data: positions, isLoading } = useTradingPositions();
  const { data: orders } = useTradingOrders("open");
  const placeOrder = usePlaceOrder();
  const closePos = useClosePosition();
  const [showOrder, setShowOrder] = useState(false);
  const [form, setForm] = useState({ symbol: "", qty: "", side: "buy", type: "market", limit: "" });

  function handleOrder() {
    placeOrder.mutate({
      symbol: form.symbol,
      qty: Number(form.qty),
      side: form.side,
      order_type: form.type,
      limit_price: form.limit ? Number(form.limit) : undefined,
    });
    setShowOrder(false);
    setForm({ symbol: "", qty: "", side: "buy", type: "market", limit: "" });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <DollarSign className="h-5 w-5 text-cyan-400" />
          <h1 className="text-lg font-bold">Paper Trading</h1>
          <span className="text-xs text-zinc-500">Alpaca Paper Account</span>
        </div>
        <Button variant="outline" size="sm" onClick={() => setShowOrder(!showOrder)} className="text-xs">New Order</Button>
      </div>

      {/* Account Summary */}
      {account && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
            <p className="text-lg font-bold text-zinc-200">${Number(account.equity).toLocaleString()}</p>
            <p className="text-xs text-zinc-500">Equity</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
            <p className="text-lg font-bold text-emerald-400">${Number(account.buying_power).toLocaleString()}</p>
            <p className="text-xs text-zinc-500">Buying Power</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
            <p className="text-lg font-bold text-zinc-300">${Number(account.cash).toLocaleString()}</p>
            <p className="text-xs text-zinc-500">Cash</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
            <p className="text-lg font-bold text-zinc-300">{String(account.day_trade_count)}</p>
            <p className="text-xs text-zinc-500">Day Trades</p>
          </div>
        </div>
      )}

      {/* Order Form */}
      {showOrder && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <div className="space-y-1"><Label className="text-xs text-zinc-400">Symbol</Label><Input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} className="h-8 bg-zinc-900" /></div>
            <div className="space-y-1"><Label className="text-xs text-zinc-400">Qty</Label><Input type="number" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} className="h-8 bg-zinc-900" /></div>
            <div className="space-y-1"><Label className="text-xs text-zinc-400">Side</Label><select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })} className="h-8 w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 text-sm"><option value="buy">Buy</option><option value="sell">Sell</option></select></div>
            <div className="space-y-1"><Label className="text-xs text-zinc-400">Type</Label><select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="h-8 w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 text-sm"><option value="market">Market</option><option value="limit">Limit</option></select></div>
            {form.type === "limit" && <div className="space-y-1"><Label className="text-xs text-zinc-400">Limit $</Label><Input type="number" value={form.limit} onChange={(e) => setForm({ ...form, limit: e.target.value })} className="h-8 bg-zinc-900" /></div>}
          </div>
          <Button size="sm" onClick={handleOrder} disabled={!form.symbol || !form.qty || placeOrder.isPending}>{placeOrder.isPending ? "Placing..." : "Place Order"}</Button>
        </div>
      )}

      {/* Positions */}
      <h2 className="text-sm font-medium text-zinc-300">Positions</h2>
      {isLoading ? <Skeleton className="h-20 w-full bg-zinc-800" /> : positions && positions.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400"><th className="px-3 py-2">Symbol</th><th className="px-3 py-2 text-right">Qty</th><th className="px-3 py-2 text-right">Entry</th><th className="px-3 py-2 text-right">Current</th><th className="px-3 py-2 text-right">P&L</th><th className="px-3 py-2">Action</th></tr></thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                  <td className="px-3 py-2"><Link href={`/chart/${p.symbol}`} className="text-cyan-400 hover:underline">{String(p.symbol)}</Link></td>
                  <td className="px-3 py-2 text-right font-mono">{String(p.qty)}</td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-400">${Number(p.entry_price).toFixed(2)}</td>
                  <td className="px-3 py-2 text-right font-mono">${Number(p.current_price).toFixed(2)}</td>
                  <td className={cn("px-3 py-2 text-right font-mono", Number(p.unrealized_pnl) >= 0 ? "text-emerald-400" : "text-red-400")}>{Number(p.unrealized_pnl) >= 0 ? "+" : ""}${Number(p.unrealized_pnl).toFixed(2)} ({Number(p.unrealized_pnl_pct).toFixed(1)}%)</td>
                  <td className="px-3 py-2"><Button size="sm" variant="outline" className="h-6 px-2 text-xs" onClick={() => closePos.mutate(String(p.symbol))}>Close</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500">No open positions.</div>}

      {/* Open Orders */}
      {orders && orders.length > 0 && (
        <>
          <h2 className="text-sm font-medium text-zinc-300">Open Orders ({orders.length})</h2>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-zinc-400"><th className="px-3 py-2">Symbol</th><th className="px-3 py-2">Side</th><th className="px-3 py-2">Type</th><th className="px-3 py-2 text-right">Qty</th><th className="px-3 py-2">Status</th></tr></thead>
              <tbody>
                {orders.map((o, i) => (
                  <tr key={i} className="border-b border-zinc-800/30"><td className="px-3 py-1.5 text-cyan-400">{String(o.symbol)}</td><td className="px-3 py-1.5">{String(o.side)}</td><td className="px-3 py-1.5">{String(o.type)}</td><td className="px-3 py-1.5 text-right font-mono">{String(o.qty)}</td><td className="px-3 py-1.5 text-zinc-400">{String(o.status)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
