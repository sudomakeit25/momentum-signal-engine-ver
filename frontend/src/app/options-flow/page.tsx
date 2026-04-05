"use client";

import { useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useOptionsFlowScan, useOptionsFlow } from "@/hooks/use-options-flow";
import {
  OptionsFlowTable,
  UnusualContractsDetail,
} from "@/components/options-flow/options-table";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function OptionsFlowPage() {
  const [lookupSymbol, setLookupSymbol] = useState("");
  const [activeSymbol, setActiveSymbol] = useState("");
  const queryClient = useQueryClient();

  const { data: scanData, isLoading: scanLoading } = useOptionsFlowScan(20);
  const { data: symbolData, isLoading: symbolLoading } =
    useOptionsFlow(activeSymbol);

  function handleLookup() {
    if (lookupSymbol.trim()) {
      setActiveSymbol(lookupSymbol.trim().toUpperCase());
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Activity className="h-5 w-5 text-cyan-400" />
          <h1 className="text-lg font-bold">Options Flow</h1>
          <span className="text-xs text-zinc-500">
            Unusual activity via Polygon.io (delayed)
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              queryClient.invalidateQueries({
                queryKey: ["options-flow-scan"],
              })
            }
            disabled={scanLoading}
            className="gap-2 text-xs"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${scanLoading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
        Detects unusual options activity by comparing volume to open interest
        (Vol/OI). Contracts with Vol/OI above 3x are flagged as unusual. Put/Call
        ratio below 0.5 signals bullish sentiment, above 1.5 signals bearish.
        Requires Polygon.io API key. Rate limited to 5 calls/min.
      </div>

      {/* Symbol Lookup */}
      <div className="flex items-center gap-2">
        <Input
          placeholder="Look up symbol (e.g. AAPL)"
          value={lookupSymbol}
          onChange={(e) => setLookupSymbol(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && handleLookup()}
          className="h-8 w-40 bg-zinc-900 text-sm"
        />
        <Button
          variant="outline"
          size="sm"
          onClick={handleLookup}
          disabled={symbolLoading || !lookupSymbol.trim()}
          className="text-xs"
        >
          {symbolLoading ? "Loading..." : "Analyze"}
        </Button>
      </div>

      {/* Single Symbol Result */}
      {activeSymbol && symbolData && (
        <div className="rounded-lg border border-cyan-800/50 bg-cyan-900/10 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="font-bold text-cyan-400">{symbolData.symbol}</span>
              <span
                className={`text-xs font-medium ${
                  symbolData.flow_sentiment === "bullish"
                    ? "text-emerald-400"
                    : symbolData.flow_sentiment === "bearish"
                      ? "text-red-400"
                      : "text-zinc-400"
                }`}
              >
                {symbolData.flow_sentiment.toUpperCase()}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-zinc-400">
              <span>
                Calls:{" "}
                <span className="text-emerald-400">
                  {symbolData.total_call_volume.toLocaleString()}
                </span>
              </span>
              <span>
                Puts:{" "}
                <span className="text-red-400">
                  {symbolData.total_put_volume.toLocaleString()}
                </span>
              </span>
              <span>
                P/C:{" "}
                <span className="font-mono">
                  {symbolData.put_call_ratio.toFixed(2)}
                </span>
              </span>
              <span>
                Unusual:{" "}
                <span className="text-amber-400">
                  {symbolData.unusual_contracts.length}
                </span>
              </span>
            </div>
          </div>
          {symbolData.alert_reasons.length > 0 && (
            <div className="space-y-1">
              {symbolData.alert_reasons.map((r, i) => (
                <p key={i} className="text-xs text-zinc-400">
                  {r}
                </p>
              ))}
            </div>
          )}
          <UnusualContractsDetail result={symbolData} />
        </div>
      )}

      {/* Scan Results */}
      <h2 className="text-sm font-medium text-zinc-300">
        Universe Scan
      </h2>

      {scanLoading && !scanData ? (
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
                Scanning options flow...
              </p>
              <p className="text-xs text-zinc-500">
                Rate limited to 5 symbols/min. This may take a few minutes.
              </p>
            </div>
          </div>
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full bg-zinc-800" />
            ))}
          </div>
        </div>
      ) : scanData && scanData.length > 0 ? (
        <OptionsFlowTable results={scanData} />
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          {!scanData
            ? "Polygon API key not configured. Add POLYGON_API_KEY to your environment."
            : "No unusual options activity detected."}
        </div>
      )}
    </div>
  );
}
