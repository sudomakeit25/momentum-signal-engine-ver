"use client";

import { useMapRecord } from "@/hooks/use-map-record";
import type { LiveSummary } from "@/hooks/use-probability-map";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { fullDate, skillText, verdictTone } from "@/lib/map-format";

function Verdict({ s }: { s: LiveSummary }) {
  if (!s.verdict) {
    return <span className="text-zinc-500">too early ({s.days["1"] ?? 0} of {s.min_days})</span>;
  }
  return <span className={verdictTone(s.verdict)}>{s.verdict}</span>;
}

function PooledVerdict({ s }: { s: LiveSummary }) {
  if (!s.verdict) {
    return (
      <span className="text-zinc-500">
        too early to judge ({s.days["1"] ?? 0} of {s.min_days} sessions scored)
      </span>
    );
  }
  return (
    <>
      the map was <span className={verdictTone(s.verdict)}>{s.verdict}</span> ({skillText(s.skill)})
    </>
  );
}

function errorVsUsual(skill: number | null): string {
  if (skill == null) return "--";
  return `${skill >= 0 ? "-" : "+"}${Math.abs(skill * 100).toFixed(1)}%`;
}

export function MapRecordSection() {
  const { data, isLoading, isError } = useMapRecord();

  return (
    <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <div>
        <h2 className="text-sm font-semibold">Probability map: live record</h2>
        <p className="text-xs text-zinc-500">
          After every close the server saves each tracked stock&apos;s probability map, then scores it once the
          sessions it covers have finished. Unlike the check on each chart page, these sessions had not happened
          when the odds were saved.
        </p>
      </div>

      {isLoading ? (
        <Skeleton className="h-32 w-full bg-zinc-800" />
      ) : isError || !data || !data.ok ? (
        <p className="text-sm text-red-400">{data?.note ?? "Could not load the live record."}</p>
      ) : !data.since || !data.pooled ? (
        <p className="text-sm text-zinc-500">{data.note ?? "Nothing recorded yet."}</p>
      ) : (
        <>
          <p className="text-xs text-zinc-400">
            Since {fullDate(data.since)}: {data.sessions_saved} sessions saved for {data.stocks} stocks, last on{" "}
            {data.last_saved ? fullDate(data.last_saved) : "--"}. All stocks together:{" "}
            <PooledVerdict s={data.pooled} />.
          </p>

          <div className="grid gap-4 lg:grid-cols-2">
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800">
                  <TableHead className="h-8 text-xs text-zinc-500">Window</TableHead>
                  <TableHead className="h-8 text-right text-xs text-zinc-500">Sessions scored</TableHead>
                  <TableHead className="h-8 text-right text-xs text-zinc-500">Error vs usual odds</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.pooled.by_window.map((w) => (
                  <TableRow key={w.sessions} className="border-zinc-800/60">
                    <TableCell className="py-1.5 text-xs">within {w.sessions} {w.sessions === 1 ? "session" : "sessions"}</TableCell>
                    <TableCell className="py-1.5 text-right text-xs tabular-nums">{w.days}</TableCell>
                    <TableCell className={cn("py-1.5 text-right text-xs tabular-nums",
                      w.skill == null ? "text-zinc-500" : w.skill >= 0 ? "text-emerald-400" : "text-amber-400")}>
                      {errorVsUsual(w.skill)}
                    </TableCell>
                  </TableRow>
                ))}
                <TableRow className="border-zinc-800/60">
                  <TableCell className="py-1.5 text-xs">next session closes 10%+, from the close</TableCell>
                  <TableCell className="py-1.5 text-right text-xs tabular-nums">{data.pooled.next.days}</TableCell>
                  <TableCell className="py-1.5 text-right text-xs tabular-nums">{errorVsUsual(data.pooled.next.skill)}</TableCell>
                </TableRow>
                <TableRow className="border-zinc-800/60">
                  <TableCell className="py-1.5 text-xs">same, from the open</TableCell>
                  <TableCell className="py-1.5 text-right text-xs tabular-nums">{data.pooled.next.open_days}</TableCell>
                  <TableCell className="py-1.5 text-right text-xs tabular-nums">{errorVsUsual(data.pooled.next.open_skill)}</TableCell>
                </TableRow>
              </TableBody>
            </Table>

            {data.pooled.bins.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800">
                    <TableHead className="h-8 text-xs text-zinc-500">When it said</TableHead>
                    <TableHead className="h-8 text-xs text-zinc-500">It happened</TableHead>
                    <TableHead className="h-8 text-right text-xs text-zinc-500">Cases</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.pooled.bins.map((b) => (
                    <TableRow key={b.lo} className="border-zinc-800/60">
                      <TableCell className="py-1.5 text-xs tabular-nums">
                        {Math.round(b.lo * 100)} to {Math.round(b.hi * 100)}% (avg {(b.said * 100).toFixed(1)}%)
                      </TableCell>
                      <TableCell className="py-1.5 text-xs tabular-nums">{(b.happened * 100).toFixed(1)}%</TableCell>
                      <TableCell className="py-1.5 text-right text-xs tabular-nums text-zinc-500">{b.n.toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>

          {data.focus && data.focus.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800">
                  <TableHead className="h-8 text-xs text-zinc-500">Stock</TableHead>
                  <TableHead className="h-8 text-right text-xs text-zinc-500">Sessions scored</TableHead>
                  <TableHead className="h-8 text-right text-xs text-zinc-500">Error vs usual odds</TableHead>
                  <TableHead className="h-8 text-right text-xs text-zinc-500">10% closes</TableHead>
                  <TableHead className="h-8 text-xs text-zinc-500">So far</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.focus.map((f) => (
                  <TableRow key={f.symbol} className="border-zinc-800/60">
                    <TableCell className="py-1.5 text-xs font-medium">{f.symbol}</TableCell>
                    <TableCell className="py-1.5 text-right text-xs tabular-nums">{f.days["1"] ?? 0}</TableCell>
                    <TableCell className="py-1.5 text-right text-xs tabular-nums">{errorVsUsual(f.skill)}</TableCell>
                    <TableCell className="py-1.5 text-right text-xs tabular-nums">{f.next.happened}</TableCell>
                    <TableCell className="py-1.5 text-xs"><Verdict s={f} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          <p className="text-xs text-zinc-500">
            &quot;Error vs usual odds&quot; compares Brier scores with each stock&apos;s plain historical frequency; a
            minus means the map was closer. A verdict appears after {data.pooled.min_days} scored sessions for all
            stocks together and {data.focus?.[0]?.min_days ?? 40} for a single stock. Sessions the server was asleep
            for are skipped, not filled in afterwards.
          </p>
        </>
      )}
    </div>
  );
}
