"use client";

import { useState } from "react";
import Link from "next/link";
import { ClipboardCheck } from "lucide-react";
import {
  useScorecard,
  type HorizonStat,
  type ScorecardRecord,
} from "@/hooks/use-spike-watch";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const HORIZONS = ["m15", "h1", "eod", "d1", "d5"] as const;
const MIN_SAMPLE = 20;

function label(kind: string): string {
  return kind.replace(/_/g, " ");
}

function tone(v: number): string {
  return v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "text-zinc-400";
}

function Stat({ s }: { s: HorizonStat }) {
  if (!s.n || s.win_pct == null || s.avg_pct == null) {
    return <span className="text-zinc-600">–</span>;
  }
  // Small samples are shown, but visibly marked: a 3-for-3 record means nothing.
  const thin = s.n < MIN_SAMPLE;
  return (
    <div className={cn(thin && "opacity-60")} title={`${s.n} alerts measured`}>
      <span className={cn("font-medium", s.win_pct >= 50 ? "text-emerald-400" : "text-red-400")}>
        {s.win_pct.toFixed(0)}%
      </span>{" "}
      <span className={cn("text-xs", tone(s.avg_pct))}>
        {s.avg_pct >= 0 ? "+" : ""}
        {s.avg_pct.toFixed(2)}%
      </span>
      <div className="text-[10px] text-zinc-600">n={s.n}</div>
    </div>
  );
}

function Outcome({ r, h }: { r: ScorecardRecord; h: (typeof HORIZONS)[number] }) {
  const v = r.outcome?.[h];
  if (v == null) return <span className="text-zinc-600">–</span>;
  return <span className={tone(v)}>{v >= 0 ? "+" : ""}{v.toFixed(2)}%</span>;
}

export default function ScorecardPage() {
  const [days, setDays] = useState(30);
  const { data, isLoading, isError } = useScorecard(days);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <ClipboardCheck className="h-5 w-5 text-emerald-400" />
          <h1 className="text-lg font-bold">Scorecard</h1>
          <span className="text-xs text-zinc-500">did the alerts work?</span>
        </div>
        <div className="flex gap-1">
          {[7, 30, 90].map((d) => (
            <Button
              key={d}
              variant={days === d ? "default" : "outline"}
              size="sm"
              className="h-7 text-xs"
              onClick={() => setDays(d)}
            >
              {d}d
            </Button>
          ))}
        </div>
      </div>

      {isError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          Could not load the scorecard.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : data && data.total_alerts === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center text-sm text-zinc-500">
          No alerts logged yet. Logging starts with the first market session after this
          feature was deployed; results fill in over the following days.
        </div>
      ) : data ? (
        <>
          <p className="text-xs text-zinc-500">
            {data.total_alerts} alerts since {data.first_date}. Each cell shows the share that
            went the alert&apos;s way and the average move in the alert&apos;s direction.
            Faded cells have fewer than {MIN_SAMPLE} measurements and should not be trusted.
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Alert type</TableHead>
                <TableHead className="text-right">Alerts</TableHead>
                {HORIZONS.map((h) => (
                  <TableHead key={h} className="text-right">{data.horizons[h]}</TableHead>
                ))}
                <TableHead className="text-right">Target / stop first</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.summary.map((row) => (
                <TableRow key={`${row.kind}-${row.direction}`}>
                  <TableCell className="font-medium capitalize">
                    {label(row.kind)}{" "}
                    <span className={row.direction === "up" ? "text-emerald-400" : "text-red-400"}>
                      {row.direction === "up" ? "↑" : "↓"}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">{row.alerts}</TableCell>
                  {HORIZONS.map((h) => (
                    <TableCell key={h} className="text-right"><Stat s={row[h]} /></TableCell>
                  ))}
                  <TableCell className="text-right text-xs">
                    {row.first_touch ? (
                      <span title={`${row.first_touch.neither} reached neither that day`}>
                        <span className="text-emerald-400">{row.first_touch.target}</span>
                        {" / "}
                        <span className="text-red-400">{row.first_touch.stop}</span>
                        <span className="text-zinc-600"> of {row.first_touch.n}</span>
                      </span>
                    ) : (
                      <span className="text-zinc-600">–</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <h2 className="pt-2 text-sm font-semibold">Recent alerts</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Alert</TableHead>
                <TableHead className="text-right">Price</TableHead>
                {HORIZONS.map((h) => (
                  <TableHead key={h} className="text-right">{data.horizons[h]}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.recent.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-xs text-zinc-500">
                    {new Date(r.ts).toLocaleString(undefined, {
                      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
                    })}
                  </TableCell>
                  <TableCell>
                    <Link href={`/chart/${r.symbol}`} className="font-medium hover:underline">
                      {r.symbol}
                    </Link>
                  </TableCell>
                  <TableCell className="text-xs capitalize">
                    {label(r.kind)} {r.direction === "up" ? "↑" : "↓"}
                  </TableCell>
                  <TableCell className="text-right">${r.price.toFixed(2)}</TableCell>
                  {HORIZONS.map((h) => (
                    <TableCell key={h} className="text-right text-xs"><Outcome r={r} h={h} /></TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </>
      ) : null}

      <div className="rounded-lg border bg-zinc-900/40 p-3 text-xs text-zinc-500">
        Each alert is logged once per symbol, type and day, at the price when it first
        appeared. Moves are signed by the alert&apos;s direction, so a positive number means
        it was right. Prices are bar closes with no slippage or fees, so real results would be
        somewhat worse. Past results do not predict future ones.
      </div>
    </div>
  );
}
