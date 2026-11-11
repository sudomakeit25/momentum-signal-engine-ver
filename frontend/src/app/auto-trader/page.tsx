"use client";

import { useState } from "react";
import Link from "next/link";
import { Bot } from "lucide-react";
import {
  useAutoTradeHistory,
  type HistoryGroup,
  type HistoryTrade,
} from "@/hooks/use-auto-trade-history";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const WINDOWS = [7, 30, 90];

function money(v: number | null | undefined): string {
  if (v == null) return "--";
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toFixed(2)}`;
}

function r(v: number | null | undefined): string {
  if (v == null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}R`;
}

function price(v: number | null | undefined): string {
  return v == null ? "--" : `$${v.toFixed(2)}`;
}

function tone(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-zinc-400";
  return v > 0 ? "text-emerald-400" : "text-red-400";
}

function day(iso: string): string {
  if (!iso) return "--";
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
}

function clock(ts: number | null): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleTimeString("en-US", {
    hour: "numeric", minute: "2-digit", timeZone: "America/New_York",
  });
}

function setupName(s: string | undefined): string {
  return s ? s.replace(/_/g, " ") : "unknown";
}

function ending(t: HistoryTrade): { text: string; cls: string } {
  if (t.outcome === "open") return { text: `open (${t.open_qty} left)`, cls: "text-cyan-400" };
  if (t.outcome === "closed outside the bot") return { text: "closed outside the bot", cls: "text-amber-400" };
  const parts = Object.keys(t.exit_reasons);
  return { text: parts.length > 1 ? parts.join(" + ") : t.exit_reason || "closed", cls: "text-zinc-300" };
}

function Tile({ label, value, sub, cls }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className={cn("text-lg font-semibold tabular-nums", cls ?? "text-zinc-200")}>{value}</div>
      {sub && <div className="text-xs text-zinc-500">{sub}</div>}
    </div>
  );
}

function GroupTable({ rows, keyName, label }: { rows: HistoryGroup[]; keyName: "date" | "setup"; label: string }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{label}</TableHead>
            <TableHead className="text-right">Trades</TableHead>
            <TableHead className="text-right">Won / lost</TableHead>
            <TableHead className="text-right">Win rate</TableHead>
            <TableHead className="text-right">Avg result</TableHead>
            <TableHead className="text-right">Profit or loss</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((g) => (
            <TableRow key={g[keyName]}>
              <TableCell className="whitespace-nowrap text-xs">
                {keyName === "date" ? day(g.date ?? "") : setupName(g.setup)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {g.trades}
                {g.open > 0 && <span className="text-zinc-500"> ({g.open} open)</span>}
              </TableCell>
              <TableCell className="text-right tabular-nums text-zinc-400">
                {g.wins} / {g.losses}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {g.win_rate == null ? "--" : `${g.win_rate.toFixed(0)}%`}
              </TableCell>
              <TableCell className={cn("text-right tabular-nums", tone(g.avg_r))}>{r(g.avg_r)}</TableCell>
              <TableCell className={cn("text-right font-medium tabular-nums", tone(g.pnl))}>{money(g.pnl)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default function AutoTraderHistoryPage() {
  const [days, setDays] = useState(30);
  const { data, isLoading, isError } = useAutoTradeHistory(days);
  const t = data?.totals;
  const trades = data?.trades ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Bot className="h-5 w-5 text-cyan-400" />
          <h1 className="text-lg font-bold">Auto-trader history</h1>
          <span className="text-xs text-zinc-500">paper account, from the broker&apos;s order history</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="mr-1 text-xs text-zinc-500">Last</span>
          {WINDOWS.map((n) => (
            <Button
              key={n}
              variant={days === n ? "default" : "outline"}
              size="sm"
              className="h-7 text-xs"
              onClick={() => setDays(n)}
            >
              {n} days
            </Button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full bg-zinc-800" />
      ) : isError || !data ? (
        <p className="text-sm text-red-400">Could not load the trade history.</p>
      ) : !data.data_ok || !t ? (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400">
          {data.note ?? "The trade history is unavailable."}
        </p>
      ) : t.trades === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 text-sm text-zinc-400">
          No trades in the last {data.days} days
          {t.not_filled > 0 ? ` (${t.not_filled} orders never filled)` : ""}. Today&apos;s activity
          and skipped setups are on the{" "}
          <Link href="/intraday" className="text-cyan-400 hover:underline">Intraday Movers</Link> page.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Tile
              label={`Profit or loss, ${data.days} days`}
              value={money(t.pnl)}
              cls={tone(t.pnl)}
              sub={`${t.closed} closed trades`}
            />
            <Tile
              label="Win rate"
              value={t.win_rate == null ? "--" : `${t.win_rate.toFixed(0)}%`}
              sub={`${t.wins} won, ${t.losses} lost`}
            />
            <Tile
              label="Average result"
              value={r(t.avg_r)}
              cls={tone(t.avg_r)}
              sub="in multiples of the risk taken"
            />
            <Tile
              label="Trades"
              value={String(t.trades)}
              sub={[
                t.open ? `${t.open} open` : "",
                t.closed_outside ? `${t.closed_outside} closed outside the bot` : "",
                t.not_filled ? `${t.not_filled} never filled` : "",
              ].filter(Boolean).join(", ") || "all closed by the bot"}
            />
          </div>

          {(t.best || t.worst) && (
            <p className="text-xs text-zinc-500">
              {t.best && <>Best: {t.best.symbol} on {day(t.best.date)}, <span className={tone(t.best.pnl)}>{money(t.best.pnl)}</span>. </>}
              {t.worst && <>Worst: {t.worst.symbol} on {day(t.worst.date)}, <span className={tone(t.worst.pnl)}>{money(t.worst.pnl)}</span>.</>}
            </p>
          )}

          <div className="space-y-2">
            <h2 className="text-sm font-semibold text-zinc-300">By setup</h2>
            <GroupTable rows={data.by_setup ?? []} keyName="setup" label="Setup" />
          </div>

          <div className="space-y-2">
            <h2 className="text-sm font-semibold text-zinc-300">By day</h2>
            <GroupTable rows={data.by_day ?? []} keyName="date" label="Day" />
          </div>

          <div className="space-y-2">
            <h2 className="text-sm font-semibold text-zinc-300">Every trade</h2>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Day</TableHead>
                    <TableHead>Trade</TableHead>
                    <TableHead>Setup</TableHead>
                    <TableHead className="text-right">Entry</TableHead>
                    <TableHead className="text-right">Stop / target</TableHead>
                    <TableHead className="text-right">Exit</TableHead>
                    <TableHead>How it ended</TableHead>
                    <TableHead className="text-right">Result</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {trades.map((x) => {
                    const end = ending(x);
                    return (
                      <TableRow key={x.client_order_id}>
                        <TableCell className="whitespace-nowrap text-xs">
                          {day(x.date)}
                          <div className="text-zinc-500">{clock(x.entry_time)}</div>
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          <span className={x.side === "buy" ? "text-emerald-400" : "text-red-400"}>
                            {x.side === "buy" ? "Long" : "Short"}
                          </span>{" "}
                          <Link href={`/chart/${x.symbol}`} className="font-medium hover:underline">
                            {x.symbol}
                          </Link>
                          <div className="text-xs text-zinc-500">{x.qty} shares</div>
                        </TableCell>
                        <TableCell className="text-xs">{setupName(x.setup)}</TableCell>
                        <TableCell className="text-right tabular-nums">{price(x.entry_price)}</TableCell>
                        <TableCell className="text-right text-xs tabular-nums text-zinc-500">
                          {price(x.stop)} / {price(x.target)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {price(x.exit_price)}
                          {x.exit_time ? <div className="text-xs text-zinc-500">{clock(x.exit_time)}</div> : null}
                        </TableCell>
                        <TableCell className={cn("text-xs", end.cls)}>{end.text}</TableCell>
                        <TableCell className={cn("text-right tabular-nums", tone(x.pnl))}>
                          {money(x.pnl)}
                          <div className="text-xs">{r(x.r_multiple)}</div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </div>
        </>
      )}

      <div className="rounded-lg border bg-zinc-900/40 p-3 text-xs text-zinc-500">
        Built from the paper account&apos;s order history at Alpaca, so it matches what actually
        filled. Only the auto-trader&apos;s own orders are shown; anything placed by hand is left out.
        Totals, win rate and average result count only trades the bot fully closed. A result of
        +1R means the trade made as much as it risked between entry and stop. Paper fills are
        simulated and can be kinder than real ones, and the signals behind these trades use prices
        about 15 minutes old. Past paper results do not predict future ones.
      </div>
    </div>
  );
}
