"use client";

import Link from "next/link";
import { Activity } from "lucide-react";
import {
  usePremarketGaps,
  useSpikeWatch,
  type PremarketGap,
  type SpikeEvent,
} from "@/hooks/use-spike-watch";
import { Skeleton } from "@/components/ui/skeleton";
import { DataDelayBanner } from "@/components/data/data-delay-banner";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<string, string> = {
  volume_ignition: "Volume ignition",
  failed_breakout: "Failed breakout",
  failed_breakdown: "Failed breakdown",
  exhaustion_top: "Exhaustion top",
  capitulation_low: "Capitulation low",
};

const GROUP_LABEL = (g: string) => g.replace(/_/g, " ");

function pct(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function clock(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function Sym({ symbol }: { symbol: string }) {
  return (
    <Link href={`/chart/${symbol}`} className="font-medium hover:underline">
      {symbol}
    </Link>
  );
}

function Headline({ text }: { text?: string }) {
  if (!text) return null;
  return <div className="truncate text-[11px] text-zinc-500" title={text}>{text}</div>;
}

function EventCard({ e }: { e: SpikeEvent }) {
  const up = e.direction === "up";
  return (
    <div className="rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sym symbol={e.symbol} />
          <span
            className={cn(
              "rounded border px-1.5 py-0.5 text-[10px] font-medium",
              up
                ? "border-emerald-500/30 bg-emerald-500/20 text-emerald-400"
                : "border-red-500/30 bg-red-500/20 text-red-400"
            )}
          >
            {KIND_LABEL[e.kind] ?? e.kind} {up ? "↑" : "↓"}
          </span>
        </div>
        <span className="text-xs text-zinc-500">
          ${e.price.toFixed(2)} · {clock(e.time)}
        </span>
      </div>
      <p className="mt-1 text-xs text-zinc-400">{e.detail}</p>
      <Headline text={e.headline} />
    </div>
  );
}

function fmtShares(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

function GapRow({ g, opened }: { g: PremarketGap; opened: boolean }) {
  const up = g.gap_pct >= 0;
  // After the open: has the stock kept, extended or given back the gap?
  const kept = opened ? g.now_pct - g.gap_pct : 0;
  return (
    <div className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sym symbol={g.symbol} />
          <span className={cn("font-medium", up ? "text-emerald-400" : "text-red-400")}>
            {pct(g.gap_pct)}
          </span>
          {g.reported && (
            <span
              title={g.surprise_pct != null ? `EPS surprise ${g.surprise_pct}%` : "Reported earnings"}
              className="rounded border border-yellow-500/30 bg-yellow-500/20 px-1 text-[10px] text-yellow-400"
            >
              REPORTED
            </span>
          )}
        </div>
        <span className="text-xs text-zinc-500">
          ${g.price.toFixed(2)} from ${g.prior_close.toFixed(2)} · {fmtShares(g.pre_volume)} shares (
          {g.day_share_pct.toFixed(1)}% of a normal day)
        </span>
      </div>
      {opened && (
        <p className="mt-1 text-xs text-zinc-400">
          Now {pct(g.now_pct)} on the day:{" "}
          <span className={kept * (up ? 1 : -1) >= 0 ? "text-emerald-400" : "text-amber-400"}>
            {Math.abs(kept) < 0.3 ? "holding the gap" : kept * (up ? 1 : -1) > 0 ? "extended" : "fading"}
          </span>
        </p>
      )}
      <Headline text={g.headline} />
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="text-xs text-zinc-500">{hint}</p>
      </div>
      {children}
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="rounded-lg border border-dashed p-4 text-xs text-zinc-500">{text}</p>;
}

export default function SpikeWatchPage() {
  const { data, isLoading, isError } = useSpikeWatch();
  const premarket = usePremarketGaps();
  const gaps = premarket.data?.gaps ?? [];
  const opened = premarket.data?.phase === "open" || premarket.data?.phase === "after";

  const spikes = (data?.events ?? []).filter((e) => e.kind === "volume_ignition");
  const reversals = (data?.events ?? []).filter((e) => e.kind !== "volume_ignition");

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Activity className="h-5 w-5 text-fuchsia-400" />
        <h1 className="text-lg font-bold">Spike Watch</h1>
        <span className="text-xs text-zinc-500">sudden spikes and reversals</span>
      </div>

      <DataDelayBanner />

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

      <Section
        title={`${opened ? "This morning's gaps" : "Pre-market gaps"} (${gaps.length})`}
        hint="Gapping 2% or more before the open, with a meaningful slice of a normal day already traded."
      >
        {(premarket.data?.notes ?? []).map((n) => (
          <p key={n} className="text-xs text-amber-400">{n}</p>
        ))}
        {premarket.isLoading ? (
          <Skeleton className="h-14 w-full" />
        ) : gaps.length ? (
          <div className="grid gap-2 md:grid-cols-2">
            {gaps.map((g) => <GapRow key={g.symbol} g={g} opened={opened} />)}
          </div>
        ) : premarket.data?.phase === "closed" ? null : (
          <Empty text="No qualifying gaps." />
        )}
      </Section>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : data ? (
        <>
          <Section
            title={`Spikes (${spikes.length})`}
            hint="A 5-minute bar at several times its usual volume for that time of day, closing through yesterday's high or low."
          >
            {spikes.length ? (
              <div className="grid gap-2 md:grid-cols-2">
                {spikes.map((e) => <EventCard key={`${e.symbol}-${e.kind}-${e.direction}`} e={e} />)}
              </div>
            ) : (
              <Empty text={data.market_open ? "None right now." : "Intraday only: resumes at the open."} />
            )}
          </Section>

          <Section
            title={`Reversals (${reversals.length})`}
            hint="Breaks of yesterday's range that failed, and very heavy days that rejected a steep run."
          >
            {reversals.length ? (
              <div className="grid gap-2 md:grid-cols-2">
                {reversals.map((e) => <EventCard key={`${e.symbol}-${e.kind}-${e.direction}`} e={e} />)}
              </div>
            ) : (
              <Empty text="None right now." />
            )}
          </Section>

          <Section
            title={`Sympathy (${data.sympathy.length})`}
            hint="One stock in a group is up 8% or more on real volume; these peers have moved less than 2%."
          >
            {data.sympathy.length ? (
              <div className="space-y-2">
                {data.sympathy.map((s) => (
                  <div key={s.group} className="rounded-lg border p-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs capitalize text-zinc-500">{GROUP_LABEL(s.group)}</span>
                      <Sym symbol={s.leader} />
                      <span className="text-emerald-400">{pct(s.leader_change_pct)}</span>
                      <span className="text-xs text-zinc-500">on {s.leader_rvol}x volume</span>
                    </div>
                    <Headline text={s.headline} />
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      <span className="text-zinc-500">Not moved yet:</span>
                      {s.laggards.map((l) => (
                        <span key={l.symbol} className="rounded border px-1.5 py-0.5">
                          <Sym symbol={l.symbol} />{" "}
                          <span className="text-zinc-500">{pct(l.change_pct)}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty text="No group has a clear leader today." />
            )}
          </Section>

          <Section
            title={`Stretched (${data.stretched.length})`}
            hint="More than 30% from where it closed five sessions ago. Not a signal: just where a reversal is most worth watching."
          >
            {data.stretched.length ? (
              <div className="grid gap-2 md:grid-cols-2">
                {data.stretched.map((s) => (
                  <div key={s.symbol} className="rounded-lg border p-3">
                    <div className="flex items-center justify-between">
                      <Sym symbol={s.symbol} />
                      <span className={cn("text-sm", s.move_5d_pct >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {pct(s.move_5d_pct)} in 5 sessions · ${s.price.toFixed(2)}
                      </span>
                    </div>
                    <Headline text={s.headline} />
                  </div>
                ))}
              </div>
            ) : (
              <Empty text="Nothing is that far from last week's price." />
            )}
          </Section>
        </>
      ) : null}

      <div className="rounded-lg border bg-zinc-900/40 p-3 text-xs text-zinc-500">
        These detectors are new and unproven. They do not send alerts. Each detection is
        logged to the <Link href="/scorecard" className="underline">Scorecard</Link>, which
        measures what the price did afterwards, so you can see which of them are worth
        acting on. This is a screen, not advice.
      </div>
    </div>
  );
}
