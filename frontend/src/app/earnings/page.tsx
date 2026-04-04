"use client";

import { useState } from "react";
import { Calendar, Plus, Trash2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const EARNINGS_KEY = "mse-earnings-dates";

interface EarningsEntry {
  symbol: string;
  date: string;
  estimate_eps?: string;
  notes?: string;
}

function loadEarnings(): EarningsEntry[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(EARNINGS_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveEarnings(entries: EarningsEntry[]) {
  localStorage.setItem(EARNINGS_KEY, JSON.stringify(entries));
}

function daysUntil(dateStr: string): number {
  const d = new Date(dateStr);
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  return Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

export default function EarningsPage() {
  const [entries, setEntries] = useState<EarningsEntry[]>(loadEarnings);
  const [symbol, setSymbol] = useState("");
  const [date, setDate] = useState("");
  const [eps, setEps] = useState("");
  const [notes, setNotes] = useState("");

  const handleAdd = () => {
    if (!symbol.trim() || !date) return;
    const updated = [
      ...entries,
      {
        symbol: symbol.toUpperCase().trim(),
        date,
        estimate_eps: eps || undefined,
        notes: notes || undefined,
      },
    ];
    setEntries(updated);
    saveEarnings(updated);
    setSymbol("");
    setDate("");
    setEps("");
    setNotes("");
  };

  const handleRemove = (idx: number) => {
    const updated = entries.filter((_, i) => i !== idx);
    setEntries(updated);
    saveEarnings(updated);
  };

  const sorted = [...entries].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
  const upcoming = sorted.filter((e) => daysUntil(e.date) >= 0);
  const past = sorted.filter((e) => daysUntil(e.date) < 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Calendar className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Earnings Calendar</h1>
      </div>

      {/* Add form */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-300">Track Earnings Date</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Symbol</label>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="AAPL"
              className="w-24 rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Earnings Date</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Est. EPS</label>
            <input
              value={eps}
              onChange={(e) => setEps(e.target.value)}
              placeholder="$2.15"
              className="w-20 rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Notes</label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Before market open"
              className="w-40 rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-500 focus:outline-none"
            />
          </div>
          <Button onClick={handleAdd} size="sm" className="bg-cyan-600 hover:bg-cyan-700">
            <Plus className="mr-1 h-3 w-3" /> Add
          </Button>
        </div>
      </div>

      {/* Upcoming earnings */}
      <div>
        <h2 className="mb-3 text-sm font-semibold text-zinc-300">
          Upcoming ({upcoming.length})
        </h2>
        {upcoming.length === 0 ? (
          <div className="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
            No upcoming earnings tracked. Add symbols above to track their earnings dates.
          </div>
        ) : (
          <div className="space-y-2">
            {upcoming.map((e, i) => {
              const days = daysUntil(e.date);
              const origIdx = entries.indexOf(e);
              return (
                <div
                  key={`${e.symbol}-${e.date}-${i}`}
                  className={cn(
                    "flex items-center justify-between rounded-lg border px-4 py-3",
                    days <= 3
                      ? "border-yellow-700 bg-yellow-950/20"
                      : "border-zinc-800 bg-zinc-900/50"
                  )}
                >
                  <div className="flex items-center gap-4">
                    {days <= 3 && <AlertTriangle className="h-4 w-4 text-yellow-400" />}
                    <span className="font-bold text-cyan-400">{e.symbol}</span>
                    <span className="text-sm text-zinc-400">
                      {new Date(e.date).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </span>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        days === 0
                          ? "bg-red-500/20 text-red-400"
                          : days <= 3
                          ? "bg-yellow-500/20 text-yellow-400"
                          : days <= 7
                          ? "bg-blue-500/20 text-blue-400"
                          : "bg-zinc-700 text-zinc-400"
                      )}
                    >
                      {days === 0 ? "Today" : days === 1 ? "Tomorrow" : `${days}d`}
                    </span>
                    {e.estimate_eps && (
                      <span className="text-xs text-zinc-500">EPS est: {e.estimate_eps}</span>
                    )}
                    {e.notes && (
                      <span className="text-xs text-zinc-500 italic">{e.notes}</span>
                    )}
                  </div>
                  <button onClick={() => handleRemove(origIdx)} className="text-zinc-500 hover:text-red-400">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Past earnings */}
      {past.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold text-zinc-300">
            Past ({past.length})
          </h2>
          <div className="space-y-2 opacity-60">
            {past.slice(-10).reverse().map((e, i) => {
              const origIdx = entries.indexOf(e);
              return (
                <div
                  key={`past-${e.symbol}-${e.date}-${i}`}
                  className="flex items-center justify-between rounded-lg border border-zinc-800/50 px-4 py-2"
                >
                  <div className="flex items-center gap-4">
                    <span className="font-bold text-zinc-400">{e.symbol}</span>
                    <span className="text-sm text-zinc-500">
                      {new Date(e.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                    </span>
                    {e.estimate_eps && <span className="text-xs text-zinc-600">EPS: {e.estimate_eps}</span>}
                  </div>
                  <button onClick={() => handleRemove(origIdx)} className="text-zinc-600 hover:text-red-400">
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tip */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3 text-xs text-zinc-500">
        <strong>Tip:</strong> Track earnings dates for stocks you hold or are watching. Avoid opening new positions
        within 3 days of earnings (yellow warning) unless you have a specific catalyst thesis. Stocks with upcoming
        earnings are highlighted in yellow.
      </div>
    </div>
  );
}
