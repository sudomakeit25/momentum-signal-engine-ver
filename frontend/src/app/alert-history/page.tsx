"use client";

import { useState, useMemo } from "react";
import { Bell, Filter, X } from "lucide-react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useAlertHistory } from "@/hooks/use-journal";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type SortKey = "timestamp" | "symbol" | "action" | "entry" | "pnl_pct" | "confidence";
type SortDir = "asc" | "desc";

export default function AlertHistoryPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useAlertHistory(500);

  const [symbolFilter, setSymbolFilter] = useState("");
  const [actionFilter, setActionFilter] = useState<"" | "BUY" | "SELL">("");
  const [setupFilter, setSetupFilter] = useState("");
  const [smsFilter, setSmsFilter] = useState<"" | "yes" | "no">("");
  const [sortKey, setSortKey] = useState<SortKey>("timestamp");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [showFilters, setShowFilters] = useState(false);

  const uniqueSymbols = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.map((a) => a.symbol as string).filter(Boolean))).sort();
  }, [data]);

  const uniqueSetups = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.map((a) => a.setup_type as string).filter(Boolean))).sort();
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let rows = [...data];
    if (symbolFilter) rows = rows.filter((a) => a.symbol === symbolFilter);
    if (actionFilter) rows = rows.filter((a) => a.action === actionFilter);
    if (setupFilter) rows = rows.filter((a) => a.setup_type === setupFilter);
    if (smsFilter === "yes") rows = rows.filter((a) => a.sms_sent);
    if (smsFilter === "no") rows = rows.filter((a) => !a.sms_sent);
    rows.sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (sortKey === "timestamp") {
        av = av ? new Date(av as string).getTime() : 0;
        bv = bv ? new Date(bv as string).getTime() : 0;
      }
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      if ((av ?? 0) < (bv ?? 0)) return sortDir === "asc" ? -1 : 1;
      if ((av ?? 0) > (bv ?? 0)) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return rows;
  }, [data, symbolFilter, actionFilter, setupFilter, smsFilter, sortKey, sortDir]);

  const activeFilterCount = [symbolFilter, actionFilter, setupFilter, smsFilter].filter(Boolean).length;

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  const SortIcon = ({ col }: { col: SortKey }) => (
    sortKey === col ? <span className="ml-1 text-cyan-400">{sortDir === "asc" ? "↑" : "↓"}</span> : null
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Bell className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Alert History</h1>
        <span className="text-xs text-zinc-500">
          {filtered.length}{data && filtered.length !== data.length ? ` / ${data.length}` : ""} alerts
        </span>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={cn(
            "ml-auto flex items-center gap-1 rounded-md border px-2 py-1 text-xs transition",
            showFilters || activeFilterCount > 0
              ? "border-cyan-600 bg-cyan-900/30 text-cyan-400"
              : "border-zinc-700 text-zinc-400 hover:border-zinc-500"
          )}
        >
          <Filter className="h-3 w-3" />
          Filters{activeFilterCount > 0 && ` (${activeFilterCount})`}
        </button>
      </div>

      {showFilters && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <select
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300"
          >
            <option value="">All symbols</option>
            {uniqueSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value as typeof actionFilter)}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300"
          >
            <option value="">All actions</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
          <select
            value={setupFilter}
            onChange={(e) => setSetupFilter(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300"
          >
            <option value="">All setups</option>
            {uniqueSetups.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select
            value={smsFilter}
            onChange={(e) => setSmsFilter(e.target.value as typeof smsFilter)}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300"
          >
            <option value="">All SMS</option>
            <option value="yes">SMS sent</option>
            <option value="no">SMS not sent</option>
          </select>
          {activeFilterCount > 0 && (
            <button
              onClick={() => { setSymbolFilter(""); setActionFilter(""); setSetupFilter(""); setSmsFilter(""); }}
              className="flex items-center gap-1 rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
            >
              <X className="h-3 w-3" /> Clear
            </button>
          )}
        </div>
      )}

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
        Every dispatched signal alert is logged here. Track which alerts
        led to profitable moves by comparing entry prices with current prices.
      </div>

      {isError ? (
        <div className="rounded-lg border border-red-800/30 bg-red-900/10 p-8 text-center">
          <p className="text-sm text-zinc-300">Failed to load data.</p>
          <button onClick={() => queryClient.invalidateQueries({ queryKey: ["alert-history"] })} className="mt-3 text-xs text-cyan-400 hover:underline">Try again</button>
        </div>
      ) : isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full bg-zinc-800" />
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                <th className="cursor-pointer px-4 py-2 font-medium hover:text-zinc-200" onClick={() => toggleSort("timestamp")}>Time<SortIcon col="timestamp" /></th>
                <th className="cursor-pointer px-4 py-2 font-medium hover:text-zinc-200" onClick={() => toggleSort("symbol")}>Symbol<SortIcon col="symbol" /></th>
                <th className="cursor-pointer px-4 py-2 font-medium hover:text-zinc-200" onClick={() => toggleSort("action")}>Action<SortIcon col="action" /></th>
                <th className="px-4 py-2 font-medium">Setup</th>
                <th className="cursor-pointer px-4 py-2 font-medium text-right hover:text-zinc-200" onClick={() => toggleSort("entry")}>Entry<SortIcon col="entry" /></th>
                <th className="px-4 py-2 font-medium text-right">Current</th>
                <th className="cursor-pointer px-4 py-2 font-medium text-right hover:text-zinc-200" onClick={() => toggleSort("pnl_pct")}>P&L<SortIcon col="pnl_pct" /></th>
                <th className="cursor-pointer px-4 py-2 font-medium text-right hover:text-zinc-200" onClick={() => toggleSort("confidence")}>Conf<SortIcon col="confidence" /></th>
                <th className="px-4 py-2 font-medium">SMS</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((alert, i) => (
                <tr
                  key={i}
                  className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                >
                  <td className="px-4 py-2 text-xs text-zinc-500">
                    {alert.timestamp
                      ? new Date(alert.timestamp as string).toLocaleString(
                          "en-US",
                          {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          }
                        )
                      : "-"}
                  </td>
                  <td className="px-4 py-2">
                    <Link
                      href={`/chart/${alert.symbol}`}
                      className="font-medium text-cyan-400 hover:underline"
                    >
                      {alert.symbol as string}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={cn(
                        "text-xs font-medium",
                        alert.action === "BUY"
                          ? "text-emerald-400"
                          : "text-red-400"
                      )}
                    >
                      {alert.action as string}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-zinc-400">
                    {alert.setup_type as string}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-xs text-zinc-300">
                    ${(alert.entry as number)?.toFixed(2)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-xs text-zinc-400">
                    {alert.current_price != null ? `$${Number(alert.current_price).toFixed(2)}` : "-"}
                  </td>
                  <td className={cn("px-4 py-2 text-right font-mono text-xs",
                    alert.pnl_pct != null
                      ? Number(alert.pnl_pct) >= 0 ? "text-emerald-400" : "text-red-400"
                      : "text-zinc-600"
                  )}>
                    {alert.pnl_pct != null ? `${Number(alert.pnl_pct) >= 0 ? "+" : ""}${Number(alert.pnl_pct).toFixed(1)}%` : "-"}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-xs text-zinc-400">
                    {((alert.confidence as number) * 100).toFixed(0)}%
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={cn(
                        "text-xs",
                        alert.sms_sent
                          ? "text-emerald-400"
                          : "text-zinc-600"
                      )}
                    >
                      {alert.sms_sent ? "Sent" : "No"}
                    </span>
                  </td>
                  <td className="max-w-[200px] truncate px-4 py-2 text-xs text-zinc-500">
                    {alert.reason as string}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : data && data.length > 0 && activeFilterCount > 0 ? (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500">
          No alerts match these filters.
          <button
            onClick={() => { setSymbolFilter(""); setActionFilter(""); setSetupFilter(""); setSmsFilter(""); }}
            className="ml-2 text-cyan-400 hover:underline"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          No alerts dispatched yet. Enable auto-alerts in the Notifications
          page and wait for signals to trigger.
        </div>
      )}
    </div>
  );
}
