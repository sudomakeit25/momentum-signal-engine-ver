"use client";

import Link from "next/link";
import { Star } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScoreBadge } from "./score-badge";
import { SignalChip } from "./signal-chip";
import { SetupTypeBadge } from "./setup-type-badge";
import type { ScanResult } from "@/types/api";

function formatVolume(vol: number): string {
  if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`;
  if (vol >= 1_000) return `${(vol / 1_000).toFixed(0)}K`;
  return vol.toString();
}

export function ScannerTable({
  results,
  isWatched,
  onToggleWatch,
}: {
  results: ScanResult[];
  isWatched?: (symbol: string) => boolean;
  onToggleWatch?: (symbol: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <Table>
        <TableHeader>
          <TableRow className="border-zinc-800 hover:bg-transparent">
            <TableHead className="w-8 text-zinc-400"></TableHead>
            <TableHead className="w-12 text-zinc-400">#</TableHead>
            <TableHead className="text-zinc-400">Symbol</TableHead>
            <TableHead className="text-right text-zinc-400">Price</TableHead>
            <TableHead className="text-right text-zinc-400">Change</TableHead>
            <TableHead className="text-right text-zinc-400">Volume</TableHead>
            <TableHead className="text-right text-zinc-400">RS</TableHead>
            <TableHead className="text-zinc-400">Score</TableHead>
            <TableHead className="text-zinc-400">Setups</TableHead>
            <TableHead className="text-zinc-400">Signals</TableHead>
            <TableHead className="text-zinc-400 min-w-[200px]">Reason</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map((r, i) => (
            <TableRow
              key={r.symbol}
              className="border-zinc-800 hover:bg-zinc-900/50"
            >
              <TableCell className="px-2">
                {onToggleWatch && (
                  <button onClick={() => onToggleWatch(r.symbol)} className="text-zinc-500 hover:text-yellow-400">
                    <Star
                      className={`h-3.5 w-3.5 ${isWatched?.(r.symbol) ? "fill-yellow-400 text-yellow-400" : ""}`}
                    />
                  </button>
                )}
              </TableCell>
              <TableCell className="font-mono text-xs text-zinc-500">
                {i + 1}
              </TableCell>
              <TableCell>
                <Link
                  href={`/chart/${r.symbol}`}
                  className="font-bold text-cyan-400 hover:text-cyan-300 hover:underline"
                >
                  {r.symbol}
                </Link>
              </TableCell>
              <TableCell className="text-right font-mono">
                ${r.price.toFixed(2)}
              </TableCell>
              <TableCell
                className={`text-right font-mono ${
                  r.change_pct >= 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {r.change_pct >= 0 ? "+" : ""}
                {r.change_pct.toFixed(2)}%
              </TableCell>
              <TableCell className="text-right font-mono text-zinc-300">
                {formatVolume(r.volume)}
              </TableCell>
              <TableCell className="text-right font-mono text-zinc-300">
                {r.relative_strength.toFixed(3)}
              </TableCell>
              <TableCell>
                <ScoreBadge score={r.score} />
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {r.setup_types.map((s) => (
                    <SetupTypeBadge key={s} type={s} />
                  ))}
                  {r.setup_types.length === 0 && (
                    <span className="text-xs text-zinc-600">-</span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {r.signals.map((s, j) => (
                    <SignalChip key={j} action={s.action} setupType={s.setup_type} />
                  ))}
                  {r.signals.length === 0 && (
                    <span className="text-xs text-zinc-600">-</span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <div className="space-y-1">
                  {r.signals.map((s, j) => (
                    <p
                      key={j}
                      className={`text-xs ${
                        s.action === "BUY" ? "text-emerald-400/80" : "text-red-400/80"
                      }`}
                    >
                      {s.reason}
                    </p>
                  ))}
                  {r.signals.length === 0 && (
                    <span className="text-xs text-zinc-600">-</span>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
