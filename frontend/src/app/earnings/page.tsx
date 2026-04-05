"use client";

import { useState } from "react";
import { Calendar, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEarningsWhisper } from "@/hooks/use-earnings";
import { EarningsTable } from "@/components/earnings/earnings-table";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

export default function EarningsPage() {
  const [daysAhead, setDaysAhead] = useState(14);
  const [minConviction, setMinConviction] = useState(0);
  const queryClient = useQueryClient();
  const { data, isLoading, isError, dataUpdatedAt } = useEarningsWhisper(
    daysAhead,
    minConviction
  );

  const updatedAt = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Calendar className="h-5 w-5 text-cyan-400" />
          <h1 className="text-lg font-bold">Earnings Whisper</h1>
          <span className="text-xs text-zinc-500">
            Conviction scoring powered by FMP
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {[7, 14, 30].map((d) => (
              <Button
                key={d}
                variant={daysAhead === d ? "default" : "outline"}
                size="sm"
                onClick={() => setDaysAhead(d)}
                className="text-xs"
              >
                {d}d
              </Button>
            ))}
          </div>
          <div className="flex gap-1">
            {[
              { label: "All", value: 0 },
              { label: "50+", value: 50 },
              { label: "70+", value: 70 },
            ].map((f) => (
              <Button
                key={f.value}
                variant={minConviction === f.value ? "default" : "outline"}
                size="sm"
                onClick={() => setMinConviction(f.value)}
                className="text-xs"
              >
                {f.label}
              </Button>
            ))}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              queryClient.invalidateQueries({
                queryKey: ["earnings-whisper"],
              })
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
        Conviction scores combine EPS surprise history, insider trading
        activity, analyst estimate revisions, and price action. Higher scores
        indicate stronger setups going into earnings. Requires FMP API key.
      </div>

      {isError ? (
        <div className="rounded-lg border border-red-800/30 bg-red-900/10 p-8 text-center">
          <p className="text-sm text-zinc-300">Failed to load data.</p>
          <button onClick={() => queryClient.invalidateQueries({ queryKey: ["earnings-whisper"] })} className="mt-3 text-xs text-cyan-400 hover:underline">Try again</button>
        </div>
      ) : isLoading && !data ? (
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
                Analyzing upcoming earnings...
              </p>
              <p className="text-xs text-zinc-500">
                Scoring conviction for stocks reporting in the next {daysAhead}{" "}
                days
              </p>
            </div>
          </div>
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full bg-zinc-800" />
            ))}
          </div>
        </div>
      ) : data && data.length > 0 ? (
        <EarningsTable results={data} />
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          {!data
            ? "FMP API key not configured. Add FMP_API_KEY to your environment."
            : "No upcoming earnings found in the next " +
              daysAhead +
              " days for stocks in the universe."}
        </div>
      )}
    </div>
  );
}
