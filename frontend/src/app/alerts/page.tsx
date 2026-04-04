"use client";

import { useState } from "react";
import { Bell, Plus, Trash2, CheckCircle, ArrowUp, ArrowDown } from "lucide-react";
import { usePriceAlerts } from "@/hooks/use-price-alerts";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function AlertsPage() {
  const { alerts, addAlert, removeAlert, clearTriggered } = usePriceAlerts();
  const [symbol, setSymbol] = useState("");
  const [target, setTarget] = useState("");
  const [direction, setDirection] = useState<"above" | "below">("above");

  const handleAdd = () => {
    if (!symbol.trim() || !target.trim()) return;
    addAlert({
      symbol: symbol.toUpperCase().trim(),
      target: parseFloat(target),
      direction,
    });
    setSymbol("");
    setTarget("");
  };

  const active = alerts.filter((a) => !a.triggered);
  const triggered = alerts.filter((a) => a.triggered);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Bell className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Price Alerts</h1>
      </div>

      {/* Add alert form */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-300">Create Alert</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Symbol</label>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="AAPL"
              className="w-28 rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Target Price</label>
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              type="number"
              step="0.01"
              placeholder="150.00"
              className="w-32 rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Direction</label>
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value as "above" | "below")}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none"
            >
              <option value="above">Crosses Above</option>
              <option value="below">Crosses Below</option>
            </select>
          </div>
          <Button onClick={handleAdd} size="sm" className="bg-cyan-600 hover:bg-cyan-700">
            <Plus className="mr-1 h-3 w-3" /> Add Alert
          </Button>
        </div>
      </div>

      {/* Active alerts */}
      <div>
        <h2 className="mb-3 text-sm font-semibold text-zinc-300">
          Active Alerts ({active.length})
        </h2>
        {active.length === 0 ? (
          <div className="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
            No active alerts. Create one above to get notified when a stock hits your target price.
          </div>
        ) : (
          <div className="space-y-2">
            {active.map((a, i) => (
              <div
                key={`${a.symbol}-${a.target}-${i}`}
                className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3"
              >
                <div className="flex items-center gap-3">
                  <span className="font-bold text-cyan-400">{a.symbol}</span>
                  <span
                    className={cn(
                      "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                      a.direction === "above"
                        ? "bg-emerald-500/20 text-emerald-400"
                        : "bg-red-500/20 text-red-400"
                    )}
                  >
                    {a.direction === "above" ? (
                      <ArrowUp className="h-3 w-3" />
                    ) : (
                      <ArrowDown className="h-3 w-3" />
                    )}
                    {a.direction}
                  </span>
                  <span className="font-mono text-sm text-zinc-300">
                    ${a.target.toFixed(2)}
                  </span>
                </div>
                <button
                  onClick={() => removeAlert(a.symbol, a.target)}
                  className="text-zinc-500 hover:text-red-400"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Triggered alerts */}
      {triggered.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-300">
              Triggered ({triggered.length})
            </h2>
            <Button
              variant="outline"
              size="sm"
              onClick={clearTriggered}
              className="text-xs"
            >
              Clear All
            </Button>
          </div>
          <div className="space-y-2">
            {triggered.map((a, i) => (
              <div
                key={`${a.symbol}-${a.target}-t-${i}`}
                className="flex items-center gap-3 rounded-lg border border-emerald-800/50 bg-emerald-950/20 px-4 py-3"
              >
                <CheckCircle className="h-4 w-4 text-emerald-400" />
                <span className="font-bold text-cyan-400">{a.symbol}</span>
                <span className="text-xs text-zinc-400">
                  hit ${a.target.toFixed(2)} ({a.direction})
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
