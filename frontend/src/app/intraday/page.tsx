"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Zap } from "lucide-react";
import { useIntradayMovers } from "@/hooks/use-intraday-movers";
import { SetupTypeBadge } from "@/components/scanner/setup-type-badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { IntradayResult, IntradayWatch, Signal } from "@/types/api";

function bestSignal(r: IntradayResult): Signal | null {
  if (!r.signals.length) return null;
  return [...r.signals].sort((a, b) => b.confidence - a.confidence)[0];
}

function watchLabel(w: IntradayWatch): string {
  if (w.watch_type === "box_forming" && w.lower != null && w.upper != null) {
    return `Box ${w.lower.toFixed(2)}-${w.upper.toFixed(2)}`;
  }
  if (w.watch_type === "vwap_tag" && w.upper != null) {
    return `At VWAP ${w.upper.toFixed(2)}`;
  }
  return w.watch_type;
}

function fmtVol(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

export default function IntradayMoversPage() {
  const [minChange, setMinChange] = useState(2);
  const [minRvol, setMinRvol] = useState(1.5);
  const [minPrice, setMinPrice] = useState(20);
  const { data, isLoading } = useIntradayMovers({
    min_change_pct: minChange,
    min_rvol: minRvol,
    min_price: minPrice,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Zap className="h-5 w-5 text-amber-400" />
          <h1 className="text-lg font-bold">Intraday Movers</h1>
          <span className="text-xs text-zinc-500">
            liquidity + volatility + a trigger · 5-min bars, today only
          </span>
        </div>
        <div className="flex items-end gap-3">
          <div>
            <Label className="text-xs">Min |chg| %</Label>
            <Input
              type="number" step="0.5" value={minChange} className="h-8 w-20"
              onChange={(e) => setMinChange(Number(e.target.value))}
            />
          </div>
          <div>
            <Label className="text-xs">Min RVOL</Label>
            <Input
              type="number" step="0.25" value={minRvol} className="h-8 w-20"
              onChange={(e) => setMinRvol(Number(e.target.value))}
            />
          </div>
          <div>
            <Label className="text-xs">Min price</Label>
            <Input
              type="number" step="5" value={minPrice} className="h-8 w-20"
              onChange={(e) => setMinPrice(Number(e.target.value))}
            />
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : !data || data.length === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center text-sm text-zinc-500">
          No qualifying movers right now. Outside market hours this is
          expected — the screen only looks at today&apos;s session.
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Symbol</TableHead>
              <TableHead className="text-right">Price</TableHead>
              <TableHead className="text-right">Chg%</TableHead>
              <TableHead className="text-right">RVOL</TableHead>
              <TableHead className="text-right">ATR%</TableHead>
              <TableHead className="text-right">Spread%</TableHead>
              <TableHead className="text-right">VWAP dist</TableHead>
              <TableHead className="text-right">Vol</TableHead>
              <TableHead>Setups</TableHead>
              <TableHead className="text-right">Entry / Stop / Target</TableHead>
              <TableHead className="text-right">R:R</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((r) => {
              const sig = bestSignal(r);
              return (
                <TableRow key={r.symbol}>
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-1.5">
                      <Link href={`/chart/${r.symbol}`} className="hover:underline">
                        {r.symbol}
                      </Link>
                      {r.earnings_soon && (
                        <span
                          title="Earnings within a day — be flat before the close"
                          className="inline-flex items-center gap-0.5 rounded border border-yellow-500/30 bg-yellow-500/20 px-1 text-[10px] text-yellow-400"
                        >
                          <AlertTriangle className="h-3 w-3" /> ERN
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">${r.price.toFixed(2)}</TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-medium",
                      r.change_pct >= 0 ? "text-emerald-400" : "text-red-400"
                    )}
                  >
                    {r.change_pct >= 0 ? "+" : ""}
                    {r.change_pct.toFixed(2)}%
                  </TableCell>
                  <TableCell className="text-right">{r.rvol.toFixed(1)}x</TableCell>
                  <TableCell className="text-right">{r.atr_pct.toFixed(1)}%</TableCell>
                  <TableCell className="text-right text-zinc-500">
                    {r.spread_pct == null ? "–" : `${r.spread_pct.toFixed(3)}%`}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right",
                      r.vwap_dist_pct >= 0 ? "text-emerald-400" : "text-red-400"
                    )}
                  >
                    {r.vwap_dist_pct >= 0 ? "+" : ""}
                    {r.vwap_dist_pct.toFixed(2)}%
                  </TableCell>
                  <TableCell className="text-right text-zinc-500">
                    {fmtVol(r.volume)}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {r.setup_types.map((t) => (
                        <SetupTypeBadge key={t} type={t} />
                      ))}
                      {(r.watches ?? []).map((w) => (
                        <span
                          key={w.watch_type}
                          title={w.detail}
                          className="inline-flex items-center rounded border border-dashed border-zinc-500/50 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400"
                        >
                          {watchLabel(w)}
                        </span>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-right text-xs tabular-nums">
                    {sig
                      ? `${sig.entry.toFixed(2)} / ${sig.stop_loss.toFixed(2)} / ${sig.target.toFixed(2)}`
                      : "–"}
                  </TableCell>
                  <TableCell className="text-right">
                    {sig ? (
                      <span className="font-medium text-cyan-400">
                        {sig.rr_ratio.toFixed(1)}
                      </span>
                    ) : (
                      "–"
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      <div className="rounded-lg border bg-zinc-900/40 p-3 text-xs text-zinc-500">
        <strong>Checklist before entry:</strong> spread + slippage &lt; 0.1% ·
        a reason it&apos;s moving (news, sector, earnings) · R:R at least 1:1.5 ·
        know exactly where you&apos;re wrong (stop under the higher low / box) ·
        flat before the close on anything flagged <em>ERN</em> (reports within
        a day, via the{" "}
        <Link href="/earnings" className="underline">Earnings</Link> calendar).
        Setups shown: {" "}
        <em>Range Break</em> (tight 30-60 min box resolving on volume),{" "}
        <em>VWAP Reclaim/Reject</em> (institutional reference line), {" "}
        <em>Higher Low</em> (pullback holding above the day low). Dashed
        badges are setups still forming, with the levels to watch: an intact
        box or price back at VWAP, before any trigger.
        Alerts for new setups go out through your configured channels during
        market hours.
      </div>
    </div>
  );
}
