"use client";

import Link from "next/link";
import type { OptionsFlowResult } from "@/types/api";
import { cn } from "@/lib/utils";

function SentimentBadge({ sentiment }: { sentiment: string }) {
  const color =
    sentiment === "bullish"
      ? "text-emerald-400 bg-emerald-400/10"
      : sentiment === "bearish"
        ? "text-red-400 bg-red-400/10"
        : "text-zinc-400 bg-zinc-400/10";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        color
      )}
    >
      {sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
    </span>
  );
}

function PcRatioDisplay({ ratio }: { ratio: number }) {
  const color =
    ratio < 0.5
      ? "text-emerald-400"
      : ratio > 1.5
        ? "text-red-400"
        : "text-zinc-300";

  return <span className={cn("font-mono", color)}>{ratio.toFixed(2)}</span>;
}

export function OptionsFlowTable({ results }: { results: OptionsFlowResult[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
            <th className="px-4 py-3 font-medium">Symbol</th>
            <th className="px-4 py-3 font-medium text-right">Call Vol</th>
            <th className="px-4 py-3 font-medium text-right">Put Vol</th>
            <th className="px-4 py-3 font-medium text-right">P/C Ratio</th>
            <th className="px-4 py-3 font-medium text-right">Unusual</th>
            <th className="px-4 py-3 font-medium">Sentiment</th>
            <th className="px-4 py-3 font-medium">Signal</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr
              key={r.symbol}
              className="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30"
            >
              <td className="px-4 py-3">
                <Link
                  href={`/chart/${r.symbol}`}
                  className="font-medium text-cyan-400 hover:underline"
                >
                  {r.symbol}
                </Link>
              </td>
              <td className="px-4 py-3 text-right font-mono text-emerald-400">
                {r.total_call_volume.toLocaleString()}
              </td>
              <td className="px-4 py-3 text-right font-mono text-red-400">
                {r.total_put_volume.toLocaleString()}
              </td>
              <td className="px-4 py-3 text-right">
                <PcRatioDisplay ratio={r.put_call_ratio} />
              </td>
              <td className="px-4 py-3 text-right">
                {r.unusual_contracts.length > 0 ? (
                  <span className="font-mono text-amber-400">
                    {r.unusual_contracts.length}
                  </span>
                ) : (
                  <span className="text-zinc-600">0</span>
                )}
              </td>
              <td className="px-4 py-3">
                <SentimentBadge sentiment={r.flow_sentiment} />
              </td>
              <td className="px-4 py-3 max-w-[250px] truncate text-xs text-zinc-500">
                {r.alert_reasons.length > 0 ? r.alert_reasons[0] : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function UnusualContractsDetail({
  result,
}: {
  result: OptionsFlowResult;
}) {
  if (!result.unusual_contracts.length) return null;

  return (
    <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-zinc-400">
            <th className="px-3 py-2 font-medium">Type</th>
            <th className="px-3 py-2 font-medium text-right">Strike</th>
            <th className="px-3 py-2 font-medium">Exp</th>
            <th className="px-3 py-2 font-medium text-right">Volume</th>
            <th className="px-3 py-2 font-medium text-right">OI</th>
            <th className="px-3 py-2 font-medium text-right">Vol/OI</th>
            <th className="px-3 py-2 font-medium text-right">IV</th>
            <th className="px-3 py-2 font-medium text-right">Price</th>
          </tr>
        </thead>
        <tbody>
          {result.unusual_contracts.slice(0, 10).map((c, i) => (
            <tr
              key={i}
              className="border-b border-zinc-800/30 transition-colors hover:bg-zinc-800/20"
            >
              <td className="px-3 py-2">
                <span
                  className={cn(
                    "font-medium",
                    c.contract_type === "call"
                      ? "text-emerald-400"
                      : "text-red-400"
                  )}
                >
                  {c.contract_type.toUpperCase()}
                </span>
              </td>
              <td className="px-3 py-2 text-right font-mono text-zinc-300">
                ${c.strike.toFixed(2)}
              </td>
              <td className="px-3 py-2 text-zinc-400">
                {new Date(c.expiration).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })}
              </td>
              <td className="px-3 py-2 text-right font-mono text-zinc-300">
                {c.volume.toLocaleString()}
              </td>
              <td className="px-3 py-2 text-right font-mono text-zinc-400">
                {c.open_interest.toLocaleString()}
              </td>
              <td className="px-3 py-2 text-right font-mono text-amber-400">
                {c.vol_oi_ratio.toFixed(1)}x
              </td>
              <td className="px-3 py-2 text-right font-mono text-zinc-400">
                {c.implied_volatility
                  ? (c.implied_volatility * 100).toFixed(0) + "%"
                  : "-"}
              </td>
              <td className="px-3 py-2 text-right font-mono text-zinc-300">
                {c.last_price ? "$" + c.last_price.toFixed(2) : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
