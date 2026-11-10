"use client";

import { useState } from "react";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAutoTrader, useAutoTraderPause } from "@/hooks/use-auto-trader";

const MODE_STYLE: Record<string, string> = {
  running: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  paused: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  halted: "bg-red-500/20 text-red-400 border-red-500/30",
  off: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
};

export function AutoTraderPanel() {
  const { data, isError } = useAutoTrader();
  const pause = useAutoTraderPause();
  const [showSkips, setShowSkips] = useState(false);

  if (isError || !data) return null;

  // Any mode not listed (refusing, stopped) is a problem state: show it red.
  const style = MODE_STYLE[data.mode] ?? MODE_STYLE.halted;
  const c = data.config;

  return (
    <div className="rounded-lg border p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Bot className="h-4 w-4 text-cyan-400" />
          <span className="font-semibold">Auto-trader (paper)</span>
          <span className={cn("rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase", style)}>
            {data.mode}
          </span>
          <span className="text-zinc-500">
            {data.date} · {data.trades.length}/{c.max_trades_per_day} trades logged · $
            {c.risk_per_trade_usd} risk per trade · max {c.max_open_positions} open ·
            halts at -${c.daily_loss_limit_usd} · no entries after {c.last_entry} ET ·
            flat by {c.flatten_at} ET
          </span>
        </div>
        {data.enabled && !(data.paused && data.resume_hint) && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            disabled={pause.isPending}
            onClick={() => pause.mutate(!data.paused)}
          >
            {data.paused ? "Resume" : "Pause"}
          </Button>
        )}
      </div>

      {!data.enabled && (
        <p className="mt-2 text-zinc-500">
          Off. It places no orders until AUTO_TRADE_ENABLED is set to true on
          the server.
        </p>
      )}
      {data.halted && <p className="mt-2 text-red-400">Stopped for today: {data.halted}</p>}
      {data.paused && data.resume_hint && (
        <p className="mt-2 text-amber-400">Paused. From this page, {data.resume_hint}.</p>
      )}
      {!data.store_ok && (
        <p className="mt-2 text-red-400">
          The state store cannot be read, so no orders are being placed.
        </p>
      )}
      {pause.isError && (
        <p className="mt-2 text-red-400">{(pause.error as Error).message}</p>
      )}

      {data.trades.length > 0 && (
        <table className="mt-2 w-full tabular-nums">
          <thead className="text-left text-zinc-500">
            <tr>
              <th className="font-normal">Time</th>
              <th className="font-normal">Symbol</th>
              <th className="font-normal">Setup</th>
              <th className="text-right font-normal">Qty</th>
              <th className="text-right font-normal">Quote at order</th>
              <th className="text-right font-normal">Stop</th>
              <th className="text-right font-normal">Target</th>
              <th className="text-right font-normal">Risk</th>
            </tr>
          </thead>
          <tbody>
            {data.trades.map((t) => (
              <tr key={t.order_id || `${t.symbol}-${t.time}`}>
                <td>{t.time}</td>
                <td className="font-medium">
                  {t.side.toUpperCase()} {t.symbol}
                </td>
                <td>{t.setup.replace(/_/g, " ")}</td>
                <td className="text-right">{t.qty}</td>
                <td className="text-right">{t.quote_at_order.toFixed(2)}</td>
                <td className="text-right">{t.stop.toFixed(2)}</td>
                <td className="text-right">{t.target.toFixed(2)}</td>
                <td className="text-right">${t.risk_usd.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data.skips.length > 0 && (
        <div className="mt-2">
          <button
            type="button"
            className="text-zinc-500 underline"
            onClick={() => setShowSkips(!showSkips)}
          >
            {showSkips ? "Hide" : "Show"} {data.skips.length} skipped setups
          </button>
          {showSkips && (
            <ul className="mt-1 space-y-0.5 text-zinc-500">
              {data.skips.map((s, i) => (
                <li key={`${s.symbol}-${s.setup}-${i}`}>
                  {s.time} {s.action} {s.symbol} ({s.setup.replace(/_/g, " ")}): {s.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
