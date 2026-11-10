"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Flame } from "lucide-react";
import {
  useCatalystWatch,
  type ReactingCatalyst,
  type UpcomingCatalyst,
} from "@/hooks/use-catalyst-watch";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const CAPS = [
  { label: "All", min: 0 },
  { label: "$1B+", min: 1e9 },
  { label: "$5B+", min: 5e9 },
  { label: "$20B+", min: 2e10 },
];

function fmtCap(v: number | null): string {
  if (v == null) return "–";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  return `$${(v / 1e6).toFixed(0)}M`;
}

function pct(v: number, digits = 1): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function when(dateStr: string, session: string): string {
  const d = new Date(`${dateStr}T12:00:00`);
  const day = d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  const part = session === "bmo" ? " before open" : session === "amc" ? " after close" : "";
  return `${day}${part}`;
}

function tone(v: number): string {
  return v >= 0 ? "text-emerald-400" : "text-red-400";
}

function byCap<T extends { market_cap: number | null }>(rows: T[], min: number): T[] {
  return min === 0 ? rows : rows.filter((r) => (r.market_cap ?? 0) >= min);
}

function Sym({ symbol, name }: { symbol: string; name: string }) {
  return (
    <div>
      <Link href={`/chart/${symbol}`} className="font-medium hover:underline">
        {symbol}
      </Link>
      <div className="max-w-[180px] truncate text-[10px] text-zinc-500">{name}</div>
    </div>
  );
}

function UpcomingTable({ rows }: { rows: UpcomingCatalyst[] }) {
  if (rows.length === 0) {
    return <p className="p-4 text-sm text-zinc-500">Nothing matches at this size.</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Symbol</TableHead>
          <TableHead>Reports</TableHead>
          <TableHead className="text-right">Score</TableHead>
          <TableHead className="text-right">Days to cover</TableHead>
          <TableHead className="text-right">Short interest chg</TableHead>
          <TableHead className="text-right">3-mo range</TableHead>
          <TableHead className="text-right">Price</TableHead>
          <TableHead className="text-right">5d</TableHead>
          <TableHead className="text-right">Mkt cap</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.symbol}>
            <TableCell>
              <div className="flex items-center gap-2">
                <Sym symbol={r.symbol} name={r.name} />
                {r.early_move && (
                  <span
                    title={`Up ${r.last_day_pct.toFixed(1)}% on ${r.last_day_rvol}x volume in the last session, before the report`}
                    className="rounded border border-amber-500/30 bg-amber-500/20 px-1 text-[10px] text-amber-400"
                  >
                    EARLY MOVE
                  </span>
                )}
              </div>
            </TableCell>
            <TableCell className="text-xs">{when(r.earnings_date, r.session)}</TableCell>
            <TableCell className="text-right font-medium text-cyan-400">{r.score.toFixed(0)}</TableCell>
            <TableCell className="text-right">{r.days_to_cover.toFixed(1)}</TableCell>
            <TableCell className={cn("text-right", r.si_change_pct > 0 ? "text-amber-400" : "text-zinc-500")}>
              {pct(r.si_change_pct)}
            </TableCell>
            <TableCell className="text-right text-xs text-zinc-400" title={`$${r.low_3m} to $${r.high_3m}`}>
              {r.range_pos.toFixed(0)}% from low
            </TableCell>
            <TableCell className="text-right">${r.price.toFixed(2)}</TableCell>
            <TableCell className={cn("text-right", tone(r.chg_5d))}>{pct(r.chg_5d)}</TableCell>
            <TableCell className="text-right text-zinc-500">{fmtCap(r.market_cap)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ReactingTable({ rows }: { rows: ReactingCatalyst[] }) {
  if (rows.length === 0) {
    return <p className="p-4 text-sm text-zinc-500">Nothing matches at this size.</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Symbol</TableHead>
          <TableHead>Reported</TableHead>
          <TableHead className="text-right">EPS surprise</TableHead>
          <TableHead className="text-right">Big day</TableHead>
          <TableHead className="text-right">Volume</TableHead>
          <TableHead className="text-right">Since then</TableHead>
          <TableHead className="text-right">Price</TableHead>
          <TableHead className="text-right">Days to cover</TableHead>
          <TableHead className="text-right">Mkt cap</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.symbol}>
            <TableCell><Sym symbol={r.symbol} name={r.name} /></TableCell>
            <TableCell className="text-xs">{when(r.earnings_date, r.session)}</TableCell>
            <TableCell className={cn("text-right", r.surprise_pct == null ? "text-zinc-500" : tone(r.surprise_pct))}>
              {r.surprise_pct == null ? "–" : pct(r.surprise_pct, 0)}
            </TableCell>
            <TableCell className="text-right font-medium text-emerald-400" title={r.reaction_date}>
              {pct(r.reaction_pct)}
            </TableCell>
            <TableCell className="text-right">{r.reaction_rvol.toFixed(1)}x</TableCell>
            <TableCell className={cn("text-right", tone(r.since_reaction_pct))}>
              {pct(r.since_reaction_pct)}
            </TableCell>
            <TableCell className="text-right">${r.price.toFixed(2)}</TableCell>
            <TableCell className="text-right text-zinc-400">
              {r.days_to_cover > 0 ? r.days_to_cover.toFixed(1) : "–"}
            </TableCell>
            <TableCell className="text-right text-zinc-500">{fmtCap(r.market_cap)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export default function CatalystWatchPage() {
  const { data, isLoading, isError } = useCatalystWatch();
  const [minCap, setMinCap] = useState(1e9);
  const [tab, setTab] = useState<"upcoming" | "reacting">("upcoming");

  const upcoming = useMemo(() => byCap(data?.upcoming ?? [], minCap), [data, minCap]);
  const reacting = useMemo(() => byCap(data?.reacting ?? [], minCap), [data, minCap]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Flame className="h-5 w-5 text-orange-400" />
          <h1 className="text-lg font-bold">Catalyst Watch</h1>
          <span className="text-xs text-zinc-500">earnings + short interest + price reaction</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="mr-1 text-xs text-zinc-500">Market cap</span>
          {CAPS.map((c) => (
            <Button
              key={c.label}
              variant={minCap === c.min ? "default" : "outline"}
              size="sm"
              className="h-7 text-xs"
              onClick={() => setMinCap(c.min)}
            >
              {c.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex gap-1">
        <Button
          variant={tab === "upcoming" ? "default" : "outline"}
          size="sm"
          onClick={() => setTab("upcoming")}
        >
          Before the report ({upcoming.length})
        </Button>
        <Button
          variant={tab === "reacting" ? "default" : "outline"}
          size="sm"
          onClick={() => setTab("reacting")}
        >
          After the report ({reacting.length})
        </Button>
      </div>

      {(data?.notes ?? []).map((n) => (
        <div key={n} className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400">
          {n}
        </div>
      ))}
      {isError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          Could not load the scan.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          <p className="text-xs text-zinc-500">
            First load takes about half a minute: it reads two weeks of earnings calendars,
            FINRA short interest, and prices for every company reporting.
          </p>
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : data ? (
        tab === "upcoming" ? <UpcomingTable rows={upcoming} /> : <ReactingTable rows={reacting} />
      ) : null}

      <div className="rounded-lg border bg-zinc-900/40 p-3 text-xs text-zinc-500">
        {tab === "upcoming" ? (
          <>
            <strong>Before the report:</strong> earnings within 5 sessions and short sellers
            who would need 3 or more days of normal volume to buy back. The score (0-100)
            measures how much energy is stored: days to cover, short interest rising, price
            near its 3-month low, and how close the report is.{" "}
            <strong>It does not predict direction.</strong> The same setup falls hard on a bad
            report. EARLY MOVE marks a sharp, heavy-volume up day before the report.
          </>
        ) : (
          <>
            <strong>After the report:</strong> reported in the last 5 sessions and had an up
            day of at least 5% on at least twice normal volume. The direction is known but the
            first leg is gone; &ldquo;Since then&rdquo; shows whether the move has held.
          </>
        )}{" "}
        Short interest is FINRA&apos;s twice-monthly report
        {data?.short_interest_date ? ` (as of ${data.short_interest_date})` : ""}, so it lags.
        Earnings dates come from Nasdaq&apos;s calendar and can change. This is a screen, not
        advice.
      </div>
    </div>
  );
}
