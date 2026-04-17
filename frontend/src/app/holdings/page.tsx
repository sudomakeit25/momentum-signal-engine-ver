"use client";

import { useState } from "react";
import Link from "next/link";
import { Briefcase } from "lucide-react";
import { apiFetch, apiPostJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Holding = { symbol: string; shares?: number };
type Analysis = {
  symbol: string;
  price?: number;
  grade?: string;
  verdict?: string;
  composite_score?: number;
  trend?: string;
  indicators?: { relative_strength?: number };
  error?: string;
};

const GRADE_COLOR: Record<string, string> = {
  A: "text-emerald-400",
  B: "text-emerald-300",
  C: "text-amber-400",
  D: "text-orange-400",
  F: "text-red-400",
};
const VERDICT_COLOR: Record<string, string> = {
  strong_buy: "bg-emerald-500/20 text-emerald-300",
  buy: "bg-emerald-500/10 text-emerald-400",
  hold: "bg-amber-500/10 text-amber-400",
  avoid: "bg-red-500/10 text-red-400",
};

function fmtMoney(n: number) {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

export default function HoldingsPage() {
  const [text, setText] = useState("");
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, Analysis>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");

  async function parseAndAnalyze() {
    setError("");
    setLoading(true);
    setAnalyses({});
    try {
      const parsed = await apiPostJson<{ holdings: Holding[] }>(
        "/portfolio/parse",
        { text },
      );
      setHoldings(parsed.holdings);

      const results = await Promise.all(
        parsed.holdings.map((h) =>
          apiFetch<Analysis>(`/analyzer/${h.symbol}`)
            .then((r) => [h.symbol, r] as const)
            .catch((e) => [h.symbol, { symbol: h.symbol, error: String(e) }] as const),
        ),
      );
      setAnalyses(Object.fromEntries(results));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const priced = holdings.map((h) => {
    const a = analyses[h.symbol];
    const price = a?.price ?? 0;
    const value = h.shares ? price * h.shares : 0;
    return { ...h, price, value, analysis: a };
  });

  const totalValue = priced.reduce((sum, h) => sum + h.value, 0);
  const verdictCounts = priced.reduce<Record<string, number>>((acc, h) => {
    const v = h.analysis?.verdict;
    if (v) acc[v] = (acc[v] ?? 0) + 1;
    return acc;
  }, {});
  const avgScore =
    priced.length > 0
      ? priced
          .map((h) => h.analysis?.composite_score ?? 0)
          .reduce((a, b) => a + b, 0) / priced.length
      : 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Briefcase className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">My Holdings</h1>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 space-y-2">
        <label className="text-xs text-zinc-400">
          Paste your portfolio (Robinhood, CSV, or one symbol per line). Shares
          are optional - if present, we compute position value.
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"RKLB\n10,400 shares\n$85.48\nMU\n900 shares\n$459.30"}
          className="h-40 w-full rounded-md border border-zinc-700 bg-zinc-900 p-2 text-xs font-mono"
        />
        <Button size="sm" onClick={parseAndAnalyze} disabled={loading || !text.trim()}>
          {loading ? "Analyzing..." : "Parse & Analyze"}
        </Button>
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>

      {priced.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="text-[10px] uppercase text-zinc-500">Total Value</div>
            <div className="mt-1 font-mono text-lg">{fmtMoney(totalValue)}</div>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="text-[10px] uppercase text-zinc-500">Holdings</div>
            <div className="mt-1 font-mono text-lg">{priced.length}</div>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="text-[10px] uppercase text-zinc-500">Avg Score</div>
            <div className="mt-1 font-mono text-lg">{avgScore.toFixed(0)}</div>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="text-[10px] uppercase text-zinc-500">Verdicts</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {Object.entries(verdictCounts).map(([v, n]) => (
                <span
                  key={v}
                  className={cn("rounded px-1.5 py-0.5 text-[10px]", VERDICT_COLOR[v] ?? "bg-zinc-800")}
                >
                  {v.replace("_", " ")} {n}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {loading && priced.length === 0 && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full bg-zinc-800" />
          ))}
        </div>
      )}

      {priced.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-xs text-zinc-400">
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2 text-right">Shares</th>
                <th className="px-3 py-2 text-right">Price</th>
                <th className="px-3 py-2 text-right">Value</th>
                <th className="px-3 py-2">Grade</th>
                <th className="px-3 py-2">Verdict</th>
                <th className="px-3 py-2 text-right">Score</th>
                <th className="px-3 py-2">Trend</th>
                <th className="px-3 py-2 text-right">RS</th>
              </tr>
            </thead>
            <tbody>
              {priced
                .slice()
                .sort((a, b) => b.value - a.value)
                .map((h) => {
                  const a = h.analysis;
                  const err = a?.error;
                  return (
                    <tr key={h.symbol} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                      <td className="px-3 py-2">
                        <Link href={`/analyzer`} className="text-cyan-400 hover:underline">
                          {h.symbol}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-zinc-400">
                        {h.shares ? h.shares.toLocaleString() : "-"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {h.price ? `$${h.price.toFixed(2)}` : "-"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {h.value ? fmtMoney(h.value) : "-"}
                      </td>
                      {err ? (
                        <td colSpan={5} className="px-3 py-2 text-xs text-zinc-500">
                          {err.slice(0, 120)}
                        </td>
                      ) : (
                        <>
                          <td className={cn("px-3 py-2 font-mono text-lg font-bold",
                            GRADE_COLOR[a?.grade ?? ""] ?? "text-zinc-400")}>
                            {a?.grade ?? "-"}
                          </td>
                          <td className="px-3 py-2">
                            <span className={cn("rounded px-1.5 py-0.5 text-[10px]",
                              VERDICT_COLOR[a?.verdict ?? ""] ?? "bg-zinc-800")}>
                              {a?.verdict?.replace("_", " ") ?? "-"}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-amber-400">
                            {a?.composite_score !== undefined ? a.composite_score.toFixed(0) : "-"}
                          </td>
                          <td className="px-3 py-2 text-xs text-zinc-500">
                            {a?.trend ?? "-"}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-zinc-400">
                            {a?.indicators?.relative_strength?.toFixed(2) ?? "-"}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
