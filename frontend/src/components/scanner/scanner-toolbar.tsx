"use client";

import { RefreshCw, Download } from "lucide-react";
import type { ScanResult } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

function exportToCsv(results: ScanResult[]) {
  const headers = ["Symbol", "Price", "Change %", "Volume", "RS", "Score", "Setups", "Signals", "Reason"];
  const rows = results.map((r) => [
    r.symbol,
    r.price.toFixed(2),
    r.change_pct.toFixed(2),
    r.volume,
    r.relative_strength.toFixed(3),
    r.score.toFixed(1),
    r.setup_types.join("; "),
    r.signals.map((s) => s.action).join("; "),
    r.signals.map((s) => s.reason).join("; "),
  ]);
  const csv = [headers, ...rows].map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `scanner-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

interface ScannerToolbarProps {
  onRefresh: () => void;
  isLoading: boolean;
  autoRefresh: boolean;
  onAutoRefreshChange: (val: boolean) => void;
  dataUpdatedAt: number;
  results?: ScanResult[];
}

export function ScannerToolbar({
  onRefresh,
  isLoading,
  autoRefresh,
  onAutoRefreshChange,
  dataUpdatedAt,
  results,
}: ScannerToolbarProps) {
  const ago = dataUpdatedAt
    ? Math.round((Date.now() - dataUpdatedAt) / 1000)
    : null;

  return (
    <div className="flex items-center gap-4">
      <Button
        variant="outline"
        size="sm"
        onClick={onRefresh}
        disabled={isLoading}
        className="gap-2"
      >
        <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
        Refresh
      </Button>

      <div className="flex items-center gap-2">
        <Switch
          id="auto-refresh"
          checked={autoRefresh}
          onCheckedChange={onAutoRefreshChange}
        />
        <Label htmlFor="auto-refresh" className="text-xs text-zinc-400">
          Auto-refresh
        </Label>
      </div>

      {results && results.length > 0 && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => exportToCsv(results)}
          className="gap-2"
        >
          <Download className="h-3.5 w-3.5" />
          CSV
        </Button>
      )}

      {ago !== null && (
        <span className="text-xs text-zinc-500">
          Updated {ago < 5 ? "just now" : `${ago}s ago`}
        </span>
      )}
    </div>
  );
}
