"use client";

import { useState } from "react";
import { Eye, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useDarkPoolScan } from "@/hooks/use-dark-pool";
import { DarkPoolTable } from "@/components/dark-pool/dark-pool-table";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

export default function DarkPoolPage() {
  const [days, setDays] = useState(20);
  const queryClient = useQueryClient();
  const { data, isLoading, dataUpdatedAt } = useDarkPoolScan(20, days);

  const updatedAt = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Eye className="h-5 w-5 text-cyan-400" />
          <h1 className="text-lg font-bold">Dark Pool Tracker</h1>
          <span className="text-xs text-zinc-500">
            FINRA Short Volume Data (T+1 delayed)
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {[10, 20, 40].map((d) => (
              <Button
                key={d}
                variant={days === d ? "default" : "outline"}
                size="sm"
                onClick={() => setDays(d)}
                className="text-xs"
              >
                {d}d
              </Button>
            ))}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              queryClient.invalidateQueries({ queryKey: ["dark-pool-scan"] })
            }
            disabled={isLoading}
            className="gap-2 text-xs"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
          {updatedAt && (
            <span className="text-xs text-zinc-500">
              Updated {updatedAt}
            </span>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
        Short volume % indicates the proportion of off-exchange (dark pool)
        trades that were short sales. Rising short volume with stable/rising
        price may indicate institutional accumulation. Data sourced from FINRA
        RegSHO daily reports.
      </div>

      {isLoading && !data ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <svg
              className="h-5 w-5 animate-spin text-cyan-400"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <div>
              <p className="text-sm font-medium text-zinc-200">
                Fetching FINRA dark pool data...
              </p>
              <p className="text-xs text-zinc-500">
                Analyzing short volume for 140+ stocks over {days} trading days
              </p>
            </div>
          </div>
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full bg-zinc-800" />
            ))}
          </div>
        </div>
      ) : data && data.length > 0 ? (
        <DarkPoolTable results={data} />
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          No dark pool data available. FINRA data may not be published on
          weekends/holidays.
        </div>
      )}
    </div>
  );
}
