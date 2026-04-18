"use client";

import Link from "next/link";
import { Rocket } from "lucide-react";
import { useIndustryRanking } from "@/hooks/use-trading";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

type Company = {
  symbol: string;
  name: string;
  market_cap: number;
  country: string;
  price: number;
  fair_value_pct: number | null;
  z_score: number | null;
  f_score: number | null;
  m_score: number | null;
  value_generation: string;
};

const PIE_COLORS = [
  "#ef4444", "#f59e0b", "#f97316", "#ec4899", "#10b981",
  "#06b6d4", "#8b5cf6", "#78350f", "#b91c1c", "#3b82f6", "#52525b",
];

function fmtCap(n: number): string {
  if (!n) return "--";
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
  return n.toString();
}

function valueGenColor(v: string): string {
  if (v === "Resilient") return "bg-emerald-500/20 text-emerald-300";
  if (v === "Robust") return "bg-teal-500/20 text-teal-300";
  if (v === "Steady") return "bg-sky-500/20 text-sky-300";
  if (v === "Weak") return "bg-red-500/20 text-red-300";
  return "bg-zinc-700 text-zinc-300";
}

export default function IndustryRankingPage({
  params,
}: {
  params: { slug: string };
}) {
  const slug = params.slug;
  const { data, isLoading } = useIndustryRanking(slug);

  const industry = (data?.industry as string) || slug;
  const companies = ((data?.companies as Company[] | undefined) ?? []);
  const country_weights = ((data?.country_weights as Record<string, number> | undefined) ?? {});
  const industry_fv = data?.industry_fair_value_pct as number | null | undefined;
  const errorMsg = (data?.error as string | undefined);

  const pieData = Object.entries(country_weights).map(([country, w], i) => ({
    country,
    weight: Math.round(w * 10000) / 100,
    color: PIE_COLORS[i % PIE_COLORS.length],
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Rocket className="h-5 w-5 text-cyan-400" />
        <div>
          <h1 className="text-xl font-bold">{industry}</h1>
          <p className="text-xs text-zinc-500">Industry rankings with Altman Z, Piotroski F, Beneish M.</p>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-2">
          <Skeleton className="h-48 w-full bg-zinc-800" />
          <Skeleton className="h-96 w-full bg-zinc-800" />
        </div>
      )}

      {errorMsg && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {errorMsg}
        </div>
      )}

      {!isLoading && !errorMsg && companies.length > 0 && (
        <>
          {/* Top stats */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="text-[10px] uppercase text-zinc-500">Companies</div>
              <div className="mt-1 font-mono text-2xl">{companies.length}</div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="text-[10px] uppercase text-zinc-500">Countries</div>
              <div className="mt-1 font-mono text-2xl">{Object.keys(country_weights).length}</div>
            </div>
            <div
              className={cn(
                "rounded-lg border p-3",
                industry_fv !== null && industry_fv !== undefined
                  ? industry_fv > 0
                    ? "border-emerald-500/30 bg-emerald-500/10"
                    : "border-red-500/30 bg-red-500/10"
                  : "border-zinc-800 bg-zinc-900/50",
              )}
            >
              <div className="text-[10px] uppercase opacity-70">Industry Fair Value (median)</div>
              <div className="mt-1 font-mono text-2xl">
                {industry_fv !== null && industry_fv !== undefined
                  ? `${industry_fv > 0 ? "+" : ""}${industry_fv.toFixed(2)}%`
                  : "--"}
              </div>
              <div className="text-[10px] opacity-80 mt-1">
                {industry_fv !== null && industry_fv !== undefined
                  ? industry_fv > 0 ? "undervalued vs price" : "overvalued vs price"
                  : "n/a"}
              </div>
            </div>
          </div>

          {/* Country pie */}
          {pieData.length > 0 && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
                Country Composition (by market cap)
              </div>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="weight"
                      nameKey="country"
                      outerRadius={80}
                      innerRadius={40}
                      strokeWidth={1}
                      stroke="#18181b"
                    >
                      {pieData.map((d, i) => (
                        <Cell key={i} fill={d.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
                      formatter={(v) => `${Number(v).toFixed(1)}%`}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-1 text-xs">
                  {pieData.slice(0, 10).map((d) => (
                    <div key={d.country} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
                        <span className="text-zinc-300">{d.country}</span>
                      </span>
                      <span className="font-mono text-zinc-400">{d.weight.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Companies table */}
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">Stock</th>
                  <th className="px-3 py-2">Country</th>
                  <th className="px-3 py-2 text-right">Market Cap</th>
                  <th className="px-3 py-2 text-right">Fair Value %</th>
                  <th className="px-3 py-2 text-right">Z</th>
                  <th className="px-3 py-2 text-right">F</th>
                  <th className="px-3 py-2 text-right">M</th>
                  <th className="px-3 py-2">Value Generation</th>
                </tr>
              </thead>
              <tbody>
                {companies.map((c, i) => (
                  <tr key={c.symbol} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                    <td className="px-3 py-2 text-zinc-500">{i + 1}</td>
                    <td className="px-3 py-2">
                      <Link href={`/instrument/${c.symbol}`} className="font-mono text-cyan-400 hover:underline">
                        {c.symbol}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-zinc-200">{c.name}</td>
                    <td className="px-3 py-2 text-xs text-zinc-400">{c.country || "--"}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtCap(c.market_cap)}</td>
                    <td
                      className={cn(
                        "px-3 py-2 text-right font-mono",
                        c.fair_value_pct === null
                          ? "text-zinc-500"
                          : c.fair_value_pct > 0
                          ? "text-emerald-400"
                          : "text-red-400",
                      )}
                    >
                      {c.fair_value_pct !== null
                        ? `${c.fair_value_pct > 0 ? "+" : ""}${c.fair_value_pct.toFixed(2)}`
                        : "--"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-zinc-300">
                      {c.z_score !== null ? c.z_score.toFixed(2) : "--"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-zinc-300">
                      {c.f_score !== null ? c.f_score : "--"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-zinc-300">
                      {c.m_score !== null ? c.m_score.toFixed(2) : "--"}
                    </td>
                    <td className="px-3 py-2">
                      <span className={cn("rounded px-1.5 py-0.5 text-[10px]", valueGenColor(c.value_generation))}>
                        {c.value_generation}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!isLoading && !errorMsg && companies.length === 0 && (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
          No companies returned. Likely the FMP key is missing or this industry slug isn&apos;t recognized.
        </div>
      )}
    </div>
  );
}
