"use client";

import { useState } from "react";
import { Eye, Upload } from "lucide-react";
import { useScan } from "@/hooks/use-scan";
import { useWatchlist } from "@/hooks/use-watchlist";
import { ScannerTable } from "@/components/scanner/scanner-table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiPostJson } from "@/lib/api";

type ParsedHolding = { symbol: string; shares?: number };

export default function WatchlistPage() {
  const { symbols, toggle, addMany, isWatched } = useWatchlist();
  const { data, isLoading } = useScan({ top: 76 });

  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("");
  const [importStatus, setImportStatus] = useState<string>("");
  const [importing, setImporting] = useState(false);

  const filtered = data?.filter((r) => symbols.includes(r.symbol)) ?? [];

  async function handleImport() {
    if (!importText.trim()) return;
    setImporting(true);
    setImportStatus("");
    try {
      const res = await apiPostJson<{ count: number; holdings: ParsedHolding[] }>(
        "/portfolio/parse",
        { text: importText },
      );
      const syms = res.holdings.map((h) => h.symbol);
      addMany(syms);
      setImportStatus(`Imported ${syms.length} tickers: ${syms.join(", ")}`);
      setImportText("");
    } catch (e) {
      setImportStatus(`Error: ${(e as Error).message}`);
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Eye className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Watchlist</h1>
        <span className="text-sm text-zinc-500">({symbols.length} stocks)</span>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto h-7 gap-1 text-xs"
          onClick={() => setShowImport((v) => !v)}
        >
          <Upload className="h-3 w-3" /> Import
        </Button>
      </div>

      {showImport && (
        <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <label className="text-xs text-zinc-400">
            Paste tickers (supports Robinhood positions, CSV, or comma lists)
          </label>
          <textarea
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder={"RKLB\n10,400 shares\nMU\n900 shares\n..."}
            className="h-32 w-full rounded-md border border-zinc-700 bg-zinc-900 p-2 text-xs font-mono"
          />
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={handleImport} disabled={importing || !importText.trim()}>
              {importing ? "Parsing..." : "Add to watchlist"}
            </Button>
            {importStatus && (
              <span className="text-xs text-zinc-400">{importStatus}</span>
            )}
          </div>
        </div>
      )}

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
            ? "No stocks in your watchlist. Star stocks from the Scanner or click Import."
            : "Your watchlisted stocks are not in the current scan results."}
        </div>
      )}
    </div>
  );
}
