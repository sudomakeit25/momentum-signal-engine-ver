"use client";

import { useState, useEffect } from "react";
import { History, TrendingUp, TrendingDown } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Signal } from "@/types/api";
import { cn } from "@/lib/utils";

const HISTORY_KEY = "mse-signal-history";

interface HistoricalSignal extends Signal {
  id: string;
  recorded_at: string;
  outcome?: "hit_target" | "hit_stop" | "active";
  exit_price?: number;
}

function loadHistory(): HistoricalSignal[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveHistory(h: HistoricalSignal[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(h));
}

export default function SignalsHistoryPage() {
  const [history, setHistory] = useState<HistoricalSignal[]>(loadHistory);
  const [filter, setFilter] = useState<"all" | "BUY" | "SELL">("all");

  const { data: signals } = useQuery({
    queryKey: ["signals", 50],
    queryFn: () => apiFetch<Signal[]>("/signals", { top: 50 }),
    refetchInterval: 60_000,
  });

  // Record new signals into history
  useEffect(() => {
    if (!signals) return;
    setHistory((prev) => {
      let updated = [...prev];
      for (const sig of signals) {
        const id = `${sig.symbol}-${sig.action}-${sig.setup_type}-${sig.timestamp}`;
        if (!updated.find((h) => h.id === id)) {
          updated.push({
            ...sig,
            id,
            recorded_at: new Date().toISOString(),
            outcome: "active",
          });
        }
      }
      // Keep last 500
      if (updated.length > 500) updated = updated.slice(-500);
      saveHistory(updated);
      return updated;
    });
  }, [signals]);

  const filtered = history
    .filter((h) => filter === "all" || h.action === filter)
    .sort((a, b) => new Date(b.recorded_at).getTime() - new Date(a.recorded_at).getTime());

  const stats = {
    total: history.length,
    buys: history.filter((h) => h.action === "BUY").length,
    sells: history.filter((h) => h.action === "SELL").length,
    avgConfidence: history.length
      ? (history.reduce((sum, h) => sum + h.confidence, 0) / history.length * 100)
      : 0,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <History className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Signal History</h1>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <p className="text-xs text-zinc-500">Total Signals</p>
          <p className="text-xl font-bold font-mono">{stats.total}</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <p className="text-xs text-zinc-500">Buy Signals</p>
          <p className="text-xl font-bold font-mono text-emerald-400">{stats.buys}</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <p className="text-xs text-zinc-500">Sell Signals</p>
          <p className="text-xl font-bold font-mono text-red-400">{stats.sells}</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <p className="text-xs text-zinc-500">Avg Confidence</p>
          <p className="text-xl font-bold font-mono">{stats.avgConfidence.toFixed(0)}%</p>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2">
        {(["all", "BUY", "SELL"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              filter === f
                ? "bg-cyan-600 text-white"
                : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
            )}
          >
            {f === "all" ? "All" : f}
          </button>
        ))}
      </div>

      {/* Signal log */}
      {filtered.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-sm text-zinc-500">
          No signals recorded yet. Signals will be automatically captured as they appear.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-xs text-zinc-400">
                <th className="px-3 py-2 text-left">Time</th>
                <th className="px-3 py-2 text-left">Symbol</th>
                <th className="px-3 py-2 text-left">Action</th>
                <th className="px-3 py-2 text-left">Setup</th>
                <th className="px-3 py-2 text-right">Entry</th>
                <th className="px-3 py-2 text-right">Stop</th>
                <th className="px-3 py-2 text-right">Target</th>
                <th className="px-3 py-2 text-right">R:R</th>
                <th className="px-3 py-2 text-right">Conf</th>
                <th className="px-3 py-2 text-left">Reason</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 100).map((h) => (
                <tr key={h.id} className="border-b border-zinc-800/50">
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-zinc-500">
                    {new Date(h.recorded_at).toLocaleDateString()}{" "}
                    {new Date(h.recorded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td className="px-3 py-2 font-bold text-cyan-400">{h.symbol}</td>
                  <td className="px-3 py-2">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                        h.action === "BUY"
                          ? "bg-emerald-500/20 text-emerald-400"
                          : "bg-red-500/20 text-red-400"
                      )}
                    >
                      {h.action === "BUY" ? (
                        <TrendingUp className="h-3 w-3" />
                      ) : (
                        <TrendingDown className="h-3 w-3" />
                      )}
                      {h.action}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-zinc-400">
                    {h.setup_type.replace(/_/g, " ")}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">${h.entry.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right font-mono text-red-400">
                    {h.stop_loss > 0 ? `$${h.stop_loss.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-emerald-400">
                    {h.target > 0 ? `$${h.target.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {h.rr_ratio > 0 ? `${h.rr_ratio.toFixed(1)}` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {(h.confidence * 100).toFixed(0)}%
                  </td>
                  <td className="max-w-[200px] truncate px-3 py-2 text-xs text-zinc-400">
                    {h.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
