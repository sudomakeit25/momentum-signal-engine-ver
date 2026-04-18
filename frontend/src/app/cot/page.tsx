"use client";

import { useState } from "react";
import { BarChart3 } from "lucide-react";
import { useCotContracts, useCotContract } from "@/hooks/use-trading";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";

type CotRow = {
  date: string;
  noncomm_net: number;
  comm_net: number;
  open_interest: number;
};

type CotSnapshot = {
  report_date: string;
  noncomm_net: number;
  noncomm_net_change: number;
  noncomm_percentile_3y: number;
  noncomm_bias: string;
  comm_net: number;
  comm_net_change: number;
  comm_percentile_3y: number;
  comm_bias: string;
  open_interest: number;
};

function fmt(n: number): string {
  const sign = n < 0 ? "-" : "";
  const a = Math.abs(n);
  if (a >= 1000) return `${sign}${(a / 1000).toFixed(1)}k`;
  return `${sign}${a}`;
}

export default function CotPage() {
  const { data: contracts } = useCotContracts();
  const [selected, setSelected] = useState("gold");
  const { data: cotData, isLoading } = useCotContract(selected);

  const snapshot = cotData?.snapshot as CotSnapshot | undefined;
  const series = ((cotData?.series as CotRow[] | undefined) ?? []).slice(-104);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <BarChart3 className="h-5 w-5 text-cyan-400" />
        <div>
          <h1 className="text-lg font-bold">Commitment of Traders (COT)</h1>
          <p className="text-xs text-zinc-500">
            Weekly positioning from the CFTC. Non-commercial = large speculators;
            Commercial = hedgers/producers. A non-commercial net at the 90th
            percentile usually signals crowded speculation.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {(contracts ?? []).map((c) => (
          <button
            key={c.key}
            onClick={() => setSelected(c.key)}
            className={cn(
              "rounded-md border px-3 py-1 text-xs transition",
              selected === c.key
                ? "border-cyan-500 bg-cyan-600 text-white"
                : "border-zinc-700 bg-zinc-900 text-zinc-200 hover:border-cyan-500/60",
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {isLoading && <Skeleton className="h-96 w-full bg-zinc-800" />}

      {!isLoading && cotData && (cotData.error as string | undefined) && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {String(cotData.error)}
        </div>
      )}

      {!isLoading && snapshot && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div
              className={cn(
                "rounded-lg border p-4",
                snapshot.noncomm_bias === "long"
                  ? "border-emerald-500/30 bg-emerald-500/10"
                  : "border-red-500/30 bg-red-500/10",
              )}
            >
              <div className="text-[10px] uppercase opacity-80">Non-Commercial (Large Specs)</div>
              <div className="mt-1 font-mono text-2xl">
                {fmt(snapshot.noncomm_net)}
              </div>
              <div className="mt-1 text-xs">
                Δ {snapshot.noncomm_net_change > 0 ? "+" : ""}
                {fmt(snapshot.noncomm_net_change)} · {snapshot.noncomm_percentile_3y.toFixed(0)}%ile (3y)
              </div>
              <div className="mt-1 text-[10px] opacity-70 uppercase">{snapshot.noncomm_bias}</div>
            </div>
            <div
              className={cn(
                "rounded-lg border p-4",
                snapshot.comm_bias === "long"
                  ? "border-emerald-500/30 bg-emerald-500/10"
                  : "border-red-500/30 bg-red-500/10",
              )}
            >
              <div className="text-[10px] uppercase opacity-80">Commercial (Hedgers)</div>
              <div className="mt-1 font-mono text-2xl">
                {fmt(snapshot.comm_net)}
              </div>
              <div className="mt-1 text-xs">
                Δ {snapshot.comm_net_change > 0 ? "+" : ""}
                {fmt(snapshot.comm_net_change)} · {snapshot.comm_percentile_3y.toFixed(0)}%ile (3y)
              </div>
              <div className="mt-1 text-[10px] opacity-70 uppercase">{snapshot.comm_bias}</div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="text-[10px] uppercase text-zinc-500">Open Interest</div>
              <div className="mt-1 font-mono text-2xl">{fmt(snapshot.open_interest)}</div>
              <div className="mt-1 text-xs text-zinc-400">
                Report date: {snapshot.report_date}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
              Net Position — last 2 years (weekly)
            </div>
            <ResponsiveContainer width="100%" height={340}>
              <LineChart data={series} margin={{ top: 10, right: 16, left: 8, bottom: 4 }}>
                <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
                <XAxis
                  dataKey="date"
                  stroke="#71717a"
                  fontSize={10}
                  tickFormatter={(d) => String(d).slice(5)}
                />
                <YAxis
                  stroke="#71717a"
                  fontSize={11}
                  tickFormatter={(v) => fmt(Number(v))}
                />
                <Tooltip
                  contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
                  formatter={(v) => fmt(Number(v))}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={0} stroke="#52525b" />
                <Line
                  type="monotone"
                  dataKey="noncomm_net"
                  name="Non-commercial"
                  stroke="#60a5fa"
                  dot={false}
                  strokeWidth={1.8}
                />
                <Line
                  type="monotone"
                  dataKey="comm_net"
                  name="Commercial"
                  stroke="#f59e0b"
                  dot={false}
                  strokeWidth={1.8}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
