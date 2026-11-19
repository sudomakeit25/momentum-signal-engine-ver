"use client";

import {
  useProbabilityMap, useProbabilityMapGaveUp, type LiveRecord, type MapCheck, type ProbabilityMapOk,
} from "@/hooks/use-probability-map";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { fullDate, skillText, verdictTone } from "@/lib/map-format";
import Link from "next/link";
import { useAlertLevels } from "@/hooks/use-alert-levels";

function odds(p: number | null | undefined): string {
  if (p == null) return "--";
  if (p > 0 && p < 0.01) return "<1%";
  if (p > 0.99 && p < 1) return ">99%";
  return `${(p * 100).toFixed(0)}%`;
}

function price(v: number): string {
  return v >= 1 ? `$${v.toFixed(2)}` : `$${v.toFixed(4)}`;
}

function day(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
}




// Cell shading: stronger for higher odds; green above the price, red below.
function shade(p: number | null, up: boolean): React.CSSProperties {
  if (p == null) return {};
  const a = 0.06 + 0.55 * Math.min(1, p);
  return { backgroundColor: up ? `rgba(16, 185, 129, ${a})` : `rgba(239, 68, 68, ${a})` };
}

function Tiles({ d }: { d: ProbabilityMapOk }) {
  const b = d.big_day;
  const ratio = d.vol_usual_pct ? d.vol_pct / d.vol_usual_pct : null;
  return (
    <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
      <div>
        <div className="text-zinc-500">Next session closes {b.level_pct}%+</div>
        <div className="text-lg font-semibold tabular-nums">
          <span className="text-emerald-400">up {odds(b.up)}</span>{" "}
          <span className="text-red-400">down {odds(b.down)}</span>
        </div>
        <div className="text-zinc-500">
          usual for it: up {odds(b.usual_up)}, down {odds(b.usual_down)}
        </div>
      </div>
      <div>
        <div className="text-zinc-500">Today, from the open</div>
        {d.today ? (
          <>
            <div className="text-lg font-semibold tabular-nums">
              <span className="text-emerald-400">up {odds(d.today.up)}</span>{" "}
              <span className="text-red-400">down {odds(d.today.down)}</span>
            </div>
            <div className="text-zinc-500">
              opened {d.today.gap_pct >= 0 ? "+" : ""}{d.today.gap_pct.toFixed(1)}% at {price(d.today.open)}
            </div>
          </>
        ) : (
          <div className="pt-1 text-zinc-500">
            {d.in_progress ? "Open not in yet" : "Updates once the next session opens"}
          </div>
        )}
      </div>
      <div>
        <div className="text-zinc-500">Moving now</div>
        <div className="text-lg font-semibold tabular-nums text-zinc-200">{d.vol_pct.toFixed(1)}% a day</div>
        <div className="text-zinc-500">
          usual for it: {d.vol_usual_pct.toFixed(1)}%
          {ratio != null && ` (${ratio.toFixed(1)}x)`}
        </div>
      </div>
      <div>
        <div className="text-zinc-500">History used</div>
        <div className="text-lg font-semibold tabular-nums text-zinc-200">{d.history_sessions} sessions</div>
        <div className="text-zinc-500">since {fullDate(d.history_from)}</div>
      </div>
    </div>
  );
}

function Grid({ d }: { d: ProbabilityMapOk }) {
  const above = d.rows.filter((r) => r.level_pct > 0);
  const below = d.rows.filter((r) => r.level_pct < 0);
  const row = (r: ProbabilityMapOk["rows"][number]) => {
    const up = r.level_pct > 0;
    const focus = Math.abs(r.level_pct) === d.big_day.level_pct;
    return (
      <TableRow key={r.level_pct} className="border-zinc-800/60">
        <TableCell className={cn("py-1.5 tabular-nums", up ? "text-emerald-400" : "text-red-400", focus && "font-semibold")}>
          {up ? "+" : ""}{r.level_pct}%
        </TableCell>
        <TableCell className="py-1.5 tabular-nums text-zinc-300">{price(r.price)}</TableCell>
        {r.odds.map((p, i) => (
          <TableCell
            key={i}
            className={cn("py-1.5 text-center tabular-nums text-zinc-100", focus && "font-semibold")}
            style={shade(p, up)}
            title={`Usual for ${d.symbol}: ${odds(r.usual[i])}`}
          >
            {odds(p)}
          </TableCell>
        ))}
      </TableRow>
    );
  };
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="border-zinc-800">
            <TableHead className="h-8 text-xs text-zinc-500">Level</TableHead>
            <TableHead className="h-8 text-xs text-zinc-500">Price</TableHead>
            {d.horizons.map((h) => (
              <TableHead key={h} className="h-8 text-center text-xs text-zinc-500">
                within {h} {h === 1 ? "session" : "sessions"}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {above.map(row)}
          <TableRow className="border-zinc-800/60 bg-zinc-800/40">
            <TableCell className="py-1 text-xs text-zinc-400">now</TableCell>
            <TableCell className="py-1 text-xs tabular-nums text-zinc-200">{price(d.last_close)}</TableCell>
            <TableCell colSpan={d.horizons.length} className="py-1 text-xs text-zinc-500">
              {day(d.as_of)} close
            </TableCell>
          </TableRow>
          {below.map(row)}
        </TableBody>
      </Table>
    </div>
  );
}

function Check({ c, symbol }: { c: MapCheck; symbol: string }) {
  const b = c.big_day;
  return (
    <div className="space-y-2 rounded border border-zinc-800 bg-zinc-950/40 p-3 text-xs">
      <div className="font-medium text-zinc-300">How accurate this has been for {symbol}</div>
      {c.verdict && c.from && c.to ? (
        <p className="text-zinc-400">
          Rerun on each of the last {c.sessions} sessions ({fullDate(c.from)} to {fullDate(c.to)}) using only what was known
          that day, the map was <span className={verdictTone(c.verdict)}>{c.verdict}</span> ({skillText(c.skill)}).
          &quot;Usual odds&quot; means how often it happened over its whole history, ignoring how much it was moving.
        </p>
      ) : (
        <p className="text-zinc-500">Not enough history to check the map for this stock.</p>
      )}
      {b && (
        <p className="text-zinc-400">
          Over the last {b.sessions} sessions ({fullDate(b.from)} to {fullDate(b.to)}), {symbol} closed 10% or
          more up or down {b.happened} {b.happened === 1 ? "time" : "times"}. The next-session odds from the
          previous close were{" "}
          <span className={verdictTone(b.verdict)}>{b.verdict}</span>
          {b.open_verdict && (
            <>; odds from the open were <span className={verdictTone(b.open_verdict)}>{b.open_verdict}</span></>
          )}
          .
        </p>
      )}
      {c.bins && c.bins.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800">
              <TableHead className="h-7 text-xs text-zinc-500">When it said</TableHead>
              <TableHead className="h-7 text-xs text-zinc-500">It happened</TableHead>
              <TableHead className="h-7 text-right text-xs text-zinc-500">Cases</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {c.bins.map((x) => (
              <TableRow key={x.lo} className="border-zinc-800/60">
                <TableCell className="py-1 tabular-nums text-zinc-300">
                  {Math.round(x.lo * 100)} to {Math.round(x.hi * 100)}% (avg {(x.said * 100).toFixed(1)}%)
                </TableCell>
                <TableCell className="py-1 tabular-nums text-zinc-200">{(x.happened * 100).toFixed(1)}%</TableCell>
                <TableCell className="py-1 text-right tabular-nums text-zinc-500">{x.n.toLocaleString()}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function Live({ live, symbol }: { live: LiveRecord | null; symbol: string }) {
  if (!live) {
    return (
      <p className="text-xs text-zinc-500">
        Live record: starts after the next close. Each evening the server saves this table and scores it once the
        sessions it covers have finished.
      </p>
    );
  }
  if (live.days == null) {
    return (
      <p className="text-xs text-zinc-500">
        {symbol} is not in the daily live record (it covers the screener&apos;s stocks and the crypto miners).
      </p>
    );
  }
  const one = live.days["1"] ?? 0;
  const twenty = live.days["20"] ?? 0;
  return (
    <p className="text-xs text-zinc-400">
      <span className="font-medium text-zinc-300">Live record</span> since {fullDate(live.since)}: {one}{" "}
      {one === 1 ? "session" : "sessions"} scored for the next session, {twenty} for 20 sessions.{" "}
      {live.verdict ? (
        <>
          So far <span className={verdictTone(live.verdict)}>{live.verdict}</span> ({skillText(live.skill)}).
        </>
      ) : (
        <>Too early to judge: a verdict needs {live.min_days} scored sessions.</>
      )}{" "}
      {live.next.days > 0 && (
        <>
          {live.next.happened === 0
            ? "No closes of 10% or more so far."
            : `${live.next.happened} ${live.next.happened === 1 ? "close" : "closes"} of 10% or more so far.`}
        </>
      )}
    </p>
  );
}

function Levels({ symbol }: { symbol: string }) {
  const { data } = useAlertLevels();
  const mine = (data?.levels ?? []).filter((l) => l.symbol === symbol);
  return (
    <p className="text-xs text-zinc-500">
      Price alerts:{" "}
      {mine.length === 0 ? (
        <>none for {symbol}.</>
      ) : (
        mine.map((l, i) => (
          <span key={l.price} className={l.hit ? "text-emerald-400" : "text-zinc-300"}>
            {i > 0 && ", "}${l.price.toFixed(2)} {l.hit ? "reached" : "waiting"}
          </span>
        ))
      )}{" "}
      <Link href="/notifications" className="text-cyan-400 hover:underline">
        Set alerts on the Notifications page
      </Link>
      .
    </p>
  );
}

export function ProbabilityMapPanel({ symbol }: { symbol: string }) {
  const { data, isLoading, isError } = useProbabilityMap(symbol);
  const gaveUp = useProbabilityMapGaveUp(symbol);
  const maxH = data?.data_ok ? Math.max(...data.horizons) : 20;

  return (
    <div className="space-y-4 rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-300">Probability map</h2>
        <span className="text-xs text-zinc-500">
          How often {symbol} has traded at or beyond each level, scaled to how much it is moving now
        </span>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full bg-zinc-800" />
      ) : isError || !data ? (
        <p className="text-sm text-red-400">Could not load the probability map.</p>
      ) : !data.data_ok && data.retry && !gaveUp ? (
        <div className="space-y-2">
          <Skeleton className="h-64 w-full bg-zinc-800" />
          <p className="text-xs text-zinc-500">
            Building the map; this can take a moment while the server catches up. It loads here on its own.
          </p>
        </div>
      ) : !data.data_ok ? (
        <p className="text-sm text-zinc-500">
          {data.retry ? "The map could not be built right now. Reload the page to try again." : data.note}
        </p>
      ) : (
        <>
          <Tiles d={data} />
          <Grid d={data} />

          {data.in_progress && (
            <p className="text-xs text-zinc-400">
              Today&apos;s session is under way. The grid counts from the {day(data.as_of)} close, so a level
              already reached today still shows its odds from that close.
            </p>
          )}

          {data.earnings.date && data.earnings.sessions_away != null && data.earnings.sessions_away <= maxH && (
            <p className="text-xs text-amber-400">
              Earnings expected {day(data.earnings.date)}, {data.earnings.sessions_away}{" "}
              {data.earnings.sessions_away === 1 ? "session" : "sessions"} away. The map does not single out
              earnings days, which often move more.
            </p>
          )}

          {data.calibration && <Check c={data.calibration} symbol={data.symbol} />}

          <Live live={data.live} symbol={data.symbol} />
          <Levels symbol={data.symbol} />

          <p className="text-xs text-zinc-500">
            Shares of past sessions, scaled to current volatility. Reaching a level means trading at or beyond it
            during regular hours at some point in the window; hover a cell for the stock&apos;s usual odds. Not a
            forecast of direction and not advice: news, earnings and halts are not modeled, and multi-day windows
            overlap, so the check has fewer independent cases than its counts suggest.
          </p>
        </>
      )}
    </div>
  );
}
