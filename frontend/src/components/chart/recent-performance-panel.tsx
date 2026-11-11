"use client";

import { useState } from "react";
import Link from "next/link";
import { useRecentPerformance, type RecentPerformance } from "@/hooks/use-recent-performance";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const WINDOWS = [5, 10, 20];

function pct(v: number | null, digits = 2): string {
  if (v == null) return "--";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function tone(v: number | null): string {
  if (v == null || v === 0) return "text-zinc-400";
  return v > 0 ? "text-emerald-400" : "text-red-400";
}

function day(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
}

function volume(v: number | null): string {
  if (v == null) return "--";
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(v);
}

function groupName(g: string | null): string {
  if (!g) return "the market";
  if (g === "custom") return "your picks";
  return g.replace(/_/g, " ");
}

function Summary({ d }: { d: RecentPerformance }) {
  return (
    <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
      <div>
        <div className="text-zinc-500">Change over {d.sessions} sessions</div>
        <div className={cn("text-lg font-semibold tabular-nums", tone(d.change_pct))}>{pct(d.change_pct)}</div>
        <div className="text-zinc-500">
          ${d.base_close.toFixed(2)} to ${d.last_close.toFixed(2)}
        </div>
      </div>
      <div>
        <div className="text-zinc-500">Range in the window</div>
        <div className="tabular-nums text-zinc-200">
          ${d.low.toFixed(2)} to ${d.high.toFixed(2)}
        </div>
        <div className="text-zinc-500">
          {d.range_pos == null ? "no range" : `now ${d.range_pos.toFixed(0)}% of the way up`}
        </div>
      </div>
      <div>
        <div className="text-zinc-500">Up and down days</div>
        <div className="tabular-nums text-zinc-200">
          {d.up_days} up, {d.down_days} down
        </div>
        <div className="text-zinc-500">
          best {pct(d.best_day?.change_pct ?? null, 1)}, worst {pct(d.worst_day?.change_pct ?? null, 1)}
        </div>
      </div>
      <div>
        <div className="text-zinc-500">Average daily move</div>
        <div className="tabular-nums text-zinc-200">
          {d.avg_abs_move == null ? "--" : `${d.avg_abs_move.toFixed(2)}%`}
        </div>
        <div className="text-zinc-500">
          {d.typical_move == null ? "no earlier history" : `normal for it: ${d.typical_move.toFixed(2)}%`}
        </div>
      </div>
    </div>
  );
}

export function RecentPerformancePanel({ symbol }: { symbol: string }) {
  const [sessions, setSessions] = useState(10);
  const { data, isLoading, isError } = useRecentPerformance(symbol, sessions);

  return (
    <div className="space-y-4 rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-300">Recent performance</h2>
        <div className="flex items-center gap-1">
          <span className="mr-1 text-xs text-zinc-500">Sessions</span>
          {WINDOWS.map((n) => (
            <Button
              key={n}
              variant={sessions === n ? "default" : "outline"}
              size="sm"
              className="h-7 text-xs"
              onClick={() => setSessions(n)}
            >
              {n}
            </Button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-48 w-full bg-zinc-800" />
      ) : isError || !data ? (
        <p className="text-sm text-red-400">Could not load recent performance.</p>
      ) : !data.data_ok ? (
        <p className="text-sm text-zinc-500">{data.note ?? "No data."}</p>
      ) : (
        <>
          <Summary d={data} />

          {data.sessions < data.sessions_requested && (
            <p className="text-xs text-amber-400">
              Only {data.sessions} sessions of history exist for {data.symbol}.
            </p>
          )}

          {data.compared.length > 0 && (
            <div className="space-y-1">
              <div className="text-xs text-zinc-500">
                Same window, against {groupName(data.peer_group)}
              </div>
              <div className="flex flex-wrap gap-2">
                <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-1 text-xs">
                  <span className="font-medium text-zinc-200">{data.symbol}</span>{" "}
                  <span className={cn("tabular-nums", tone(data.change_pct))}>{pct(data.change_pct, 1)}</span>
                </span>
                {data.compared.map((c) => (
                  <Link
                    key={c.symbol}
                    href={`/chart/${c.symbol}`}
                    className="rounded border border-zinc-700 bg-zinc-800/60 px-2 py-1 text-xs hover:border-zinc-500"
                  >
                    <span className="font-medium text-zinc-300">{c.symbol}</span>
                    {c.is_market && <span className="text-zinc-500"> (market)</span>}{" "}
                    <span className={cn("tabular-nums", tone(c.change_pct))}>{pct(c.change_pct, 1)}</span>
                  </Link>
                ))}
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead className="text-right">Close</TableHead>
                  <TableHead className="text-right">Day</TableHead>
                  <TableHead className="text-right">Low to high</TableHead>
                  <TableHead className="text-right">Volume</TableHead>
                  <TableHead className="text-right">vs normal</TableHead>
                  <TableHead className="text-right">Since {day(data.base_date)}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...data.rows].reverse().map((r, i) => (
                  <TableRow key={r.date} className={r.big ? "bg-amber-500/5" : undefined}>
                    <TableCell className="whitespace-nowrap text-xs">
                      {day(r.date)}
                      {i === 0 && data.in_progress && (
                        <span className="ml-1 text-[10px] text-amber-400">in progress</span>
                      )}
                      {r.big && <span className="ml-1 text-[10px] text-amber-400">big day</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">${r.close.toFixed(2)}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", tone(r.change_pct))}>
                      {pct(r.change_pct)}
                    </TableCell>
                    <TableCell className="text-right text-xs tabular-nums text-zinc-500">
                      {r.low != null && r.high != null ? `$${r.low.toFixed(2)} to $${r.high.toFixed(2)}` : "--"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-zinc-400">{volume(r.volume)}</TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums",
                        r.rvol != null && r.rvol >= 1.5 ? "text-amber-400" : "text-zinc-500"
                      )}
                    >
                      {r.rvol == null ? "--" : `${r.rvol.toFixed(1)}x`}
                    </TableCell>
                    <TableCell className={cn("text-right tabular-nums", tone(r.cum_pct))}>
                      {pct(r.cum_pct)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {data.big_days.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-zinc-500">
                Headlines from the biggest days
                {data.big_day_rule ? ` (a big day is ${data.big_day_rule})` : ""}
              </div>
              {[...data.big_days]
                .sort((a, b) => (a.date < b.date ? 1 : -1))
                .map((e) => (
                  <div key={e.date} className="rounded border border-zinc-800 bg-zinc-900/60 p-2 text-xs">
                    <div className="mb-1">
                      <span className="text-zinc-300">{day(e.date)}</span>{" "}
                      <span className={cn("tabular-nums", tone(e.change_pct))}>{pct(e.change_pct, 1)}</span>
                      {e.rvol != null && <span className="text-zinc-500"> on {e.rvol.toFixed(1)}x volume</span>}
                    </div>
                    {e.headlines == null ? (
                      <div className="text-zinc-600">Headlines could not be loaded.</div>
                    ) : e.headlines.length === 0 ? (
                      <div className="text-zinc-600">No headlines found for this day.</div>
                    ) : (
                      <ul className="space-y-1">
                        {e.headlines.map((h) => (
                          <li key={h.url + h.time}>
                            {/^https?:\/\//.test(h.url) ? (
                              <a
                                href={h.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-zinc-300 hover:underline"
                              >
                                {h.headline}
                              </a>
                            ) : (
                              <span className="text-zinc-300">{h.headline}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
            </div>
          )}

          <p className="text-[11px] text-zinc-600">
            Daily bars, adjusted for splits and dividends.
            {data.in_progress
              ? " Today's row is still forming and can be up to about 35 minutes behind (15 minutes of market data delay plus caching)."
              : ""}{" "}
            A headline on the same day is not proof it caused the move. This describes what the
            price did; it is not advice.
          </p>
        </>
      )}
    </div>
  );
}
