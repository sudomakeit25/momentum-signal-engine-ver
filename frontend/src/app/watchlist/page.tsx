"use client";

import { Eye } from "lucide-react";
import { useScan } from "@/hooks/use-scan";
import { useWatchlist } from "@/hooks/use-watchlist";
import { ScannerTable } from "@/components/scanner/scanner-table";
import { Skeleton } from "@/components/ui/skeleton";

export default function WatchlistPage() {
  const { symbols, toggle, isWatched } = useWatchlist();
  const { data, isLoading } = useScan({ top: 76 });

  const filtered = data?.filter((r) => symbols.includes(r.symbol)) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Eye className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Watchlist</h1>
        <span className="text-sm text-zinc-500">({symbols.length} stocks)</span>
      </div>

      {isLoading && !data ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full bg-zinc-800" />
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <ScannerTable results={filtered} isWatched={isWatched} onToggleWatch={toggle} />
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          {symbols.length === 0
            ? "No stocks in your watchlist. Star stocks from the Scanner to add them here."
            : "Your watchlisted stocks are not in the current scan results."}
        </div>
      )}
    </div>
  );
}
