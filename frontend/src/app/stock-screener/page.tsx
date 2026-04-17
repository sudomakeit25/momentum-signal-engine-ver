"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { useProfileScreenerMeta, useProfileScreenerRun } from "@/hooks/use-trading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Profile = {
  key: string;
  label: string;
  sector: string;
  max_fwd_pe: number | null;
  min_momentum_6m: number | null;
  min_rev_growth: number | null;
  min_cap_billions: number | null;
};

type Row = {
  ticker: string;
  name: string;
  price: number;
  cap: number;
  fwd_pe: number | null;
  trail_pe: number | null;
  chg_6m: number;
  rev_growth: number;
  sector: string;
  industry: string;
};

type Filters = {
  sector: string;
  pe: string;
  mom: string;
  rev: string;
  cap: string;
  custom: string;
};

const EMPTY_FILTERS: Filters = { sector: "semiconductors", pe: "", mom: "", rev: "", cap: "", custom: "" };

function profileToFilters(p: Profile): Filters {
  return {
    sector: p.sector,
    pe: p.max_fwd_pe !== null ? String(p.max_fwd_pe) : "",
    mom: p.min_momentum_6m !== null ? String(p.min_momentum_6m) : "",
    rev: p.min_rev_growth !== null ? String(p.min_rev_growth) : "",
    cap: p.min_cap_billions !== null ? String(p.min_cap_billions) : "",
    custom: "",
  };
}

function fmtCap(cap: number) {
  if (cap >= 1e12) return `$${(cap / 1e12).toFixed(2)}T`;
  if (cap >= 1e9) return `$${(cap / 1e9).toFixed(1)}B`;
  if (cap >= 1e6) return `$${(cap / 1e6).toFixed(0)}M`;
  return `$${cap.toLocaleString()}`;
}

export default function StockScreenerPage() {
  const { data: meta } = useProfileScreenerMeta();
  const profiles = useMemo(
    () => (meta?.profiles as Profile[] | undefined) ?? [],
    [meta]
  );
  const sectors = useMemo(
    () => (meta?.sectors as string[] | undefined) ?? [],
    [meta]
  );

  const [activeProfile, setActiveProfile] = useState("like_mu");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [runCount, setRunCount] = useState(0);

  // When profiles load or user picks one, seed the filter inputs.
  useEffect(() => {
    const p = profiles.find((x) => x.key === activeProfile);
    if (p) setFilters(profileToFilters(p));
  }, [profiles, activeProfile]);

  const runParams = useMemo(() => {
    const p: Record<string, string | number | undefined> = { sector: filters.sector };
    if (filters.pe) p.max_fwd_pe = Number(filters.pe);
    if (filters.mom) p.min_momentum = Number(filters.mom);
    if (filters.rev) p.min_rev_growth = Number(filters.rev);
    if (filters.cap) p.min_cap = Number(filters.cap) * 1e9;
    if (filters.custom) p.custom = filters.custom;
    return p;
  }, [filters]);

  const { data: runData, isFetching } = useProfileScreenerRun(runParams, runCount > 0);
  const rows = (runData?.results as Row[] | undefined) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Search className="h-5 w-5 text-cyan-400" />
        <div>
          <h1 className="text-lg font-bold">Stock Screener</h1>
          <p className="text-xs text-zinc-500">Find stocks matching a profile. Live data from Yahoo Finance, cached 30 min.</p>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-4">
        <div className="flex flex-wrap gap-2">
          {profiles.map((p) => (
            <button
              key={p.key}
              onClick={() => setActiveProfile(p.key)}
              className={cn(
                "rounded-md border px-3 py-1.5 text-xs font-medium transition",
                activeProfile === p.key
                  ? "border-cyan-500 bg-cyan-500 text-black"
                  : "border-zinc-700 text-zinc-300 hover:border-cyan-500/60 hover:text-cyan-300"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <div className="space-y-1">
            <Label className="text-[10px] uppercase text-zinc-400">Sector</Label>
            <select
              value={filters.sector}
              onChange={(e) => setFilters({ ...filters, sector: e.target.value })}
              className="h-8 w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 text-xs"
            >
              {sectors.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase text-zinc-400">Max Forward P/E</Label>
            <Input
              value={filters.pe}
              onChange={(e) => setFilters({ ...filters, pe: e.target.value })}
              placeholder="30"
              className="h-8 bg-zinc-900 text-xs"
              inputMode="numeric"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase text-zinc-400">Min 6mo Momentum %</Label>
            <Input
              value={filters.mom}
              onChange={(e) => setFilters({ ...filters, mom: e.target.value })}
              placeholder="e.g. 10"
              className="h-8 bg-zinc-900 text-xs"
              inputMode="numeric"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase text-zinc-400">Min Revenue Growth %</Label>
            <Input
              value={filters.rev}
              onChange={(e) => setFilters({ ...filters, rev: e.target.value })}
              placeholder="e.g. 20"
              className="h-8 bg-zinc-900 text-xs"
              inputMode="numeric"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase text-zinc-400">Min Market Cap ($B)</Label>
            <Input
              value={filters.cap}
              onChange={(e) => setFilters({ ...filters, cap: e.target.value })}
              placeholder="5"
              className="h-8 bg-zinc-900 text-xs"
              inputMode="numeric"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase text-zinc-400">Custom Tickers (comma)</Label>
            <Input
              value={filters.custom}
              onChange={(e) => setFilters({ ...filters, custom: e.target.value })}
              placeholder="AAPL, MSFT, NVDA"
              className="h-8 bg-zinc-900 text-xs"
            />
          </div>
        </div>

        <div className="flex justify-end">
          <Button size="sm" onClick={() => setRunCount((c) => c + 1)} disabled={isFetching}>
            {isFetching ? "Scanning live data..." : "Screen"}
          </Button>
        </div>
      </div>

      {isFetching && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full bg-zinc-800" />
          ))}
        </div>
      )}

      {!isFetching && runData && rows.length === 0 && (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
          No stocks match these filters. Try relaxing a criterion.
        </div>
      )}

      {!isFetching && rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                <th className="px-3 py-2">Ticker</th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2 text-right">Price</th>
                <th className="px-3 py-2 text-right">Fwd P/E</th>
                <th className="px-3 py-2 text-right">Trail P/E</th>
                <th className="px-3 py-2 text-right">Rev Growth</th>
                <th className="px-3 py-2 text-right">6mo %</th>
                <th className="px-3 py-2 text-right">Market Cap</th>
                <th className="px-3 py-2">Industry</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                  <td className="px-3 py-2">
                    <Link href={`/chart/${r.ticker}`} className="font-mono text-cyan-400 hover:underline">
                      {r.ticker}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-xs text-zinc-300">{r.name}</td>
                  <td className="px-3 py-2 text-right font-mono">${r.price.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right font-mono">{r.fwd_pe !== null ? r.fwd_pe.toFixed(1) : "-"}</td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-400">
                    {r.trail_pe !== null ? r.trail_pe.toFixed(1) : "-"}
                  </td>
                  <td
                    className={cn(
                      "px-3 py-2 text-right font-mono",
                      r.rev_growth > 0 ? "text-emerald-400" : r.rev_growth < 0 ? "text-red-400" : "text-zinc-400"
                    )}
                  >
                    {r.rev_growth > 0 ? "+" : ""}
                    {r.rev_growth.toFixed(1)}%
                  </td>
                  <td
                    className={cn(
                      "px-3 py-2 text-right font-mono",
                      r.chg_6m >= 0 ? "text-emerald-400" : "text-red-400"
                    )}
                  >
                    {r.chg_6m >= 0 ? "+" : ""}
                    {r.chg_6m.toFixed(1)}%
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-400">{fmtCap(r.cap)}</td>
                  <td className="px-3 py-2 text-xs text-zinc-500">{r.industry}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
