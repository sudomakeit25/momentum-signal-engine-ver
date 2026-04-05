"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useAlertHistory } from "@/hooks/use-journal";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function AlertHistoryPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useAlertHistory(200);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Bell className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Alert History</h1>
        <span className="text-xs text-zinc-500">
          {data?.length || 0} alerts logged
        </span>
      </div>

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
      ) : data && data.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                <th className="px-4 py-2 font-medium">Time</th>
                <th className="px-4 py-2 font-medium">Symbol</th>
                <th className="px-4 py-2 font-medium">Action</th>
                <th className="px-4 py-2 font-medium">Setup</th>
                <th className="px-4 py-2 font-medium text-right">Entry</th>
                <th className="px-4 py-2 font-medium text-right">Conf</th>
                <th className="px-4 py-2 font-medium">SMS</th>
                <th className="px-4 py-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {data.map((alert, i) => (
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
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          No alerts dispatched yet. Enable auto-alerts in the Notifications
          page and wait for signals to trigger.
        </div>
      )}
    </div>
  );
}
