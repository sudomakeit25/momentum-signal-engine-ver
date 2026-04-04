"use client";

import { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ScanSearch } from "lucide-react";
import { useScan } from "@/hooks/use-scan";
import { ScannerTable } from "@/components/scanner/scanner-table";
import { ScannerToolbar } from "@/components/scanner/scanner-toolbar";
import { useWatchlist } from "@/hooks/use-watchlist";
import { BreadthWidget } from "@/components/scanner/breadth-widget";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

const PRESETS = [
  { label: "All Momentum", top: 20, minPrice: 5, maxPrice: 500, minVolume: 500000 },
  { label: "Large Caps", top: 20, minPrice: 50, maxPrice: 500, minVolume: 2000000 },
  { label: "Mid Caps", top: 20, minPrice: 10, maxPrice: 100, minVolume: 500000 },
  { label: "High Volume", top: 20, minPrice: 5, maxPrice: 500, minVolume: 5000000 },
  { label: "Penny Movers", top: 20, minPrice: 5, maxPrice: 30, minVolume: 1000000 },
];

export default function ScannerPage() {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [top, setTop] = useState(20);
  const [minPrice, setMinPrice] = useState(5);
  const [maxPrice, setMaxPrice] = useState(500);
  const [minVolume, setMinVolume] = useState(500000);
  const [showFilters, setShowFilters] = useState(false);
  const [activePreset, setActivePreset] = useState("All Momentum");
  const { toggle, isWatched } = useWatchlist();

  function applyPreset(preset: typeof PRESETS[number]) {
    setTop(preset.top);
    setMinPrice(preset.minPrice);
    setMaxPrice(preset.maxPrice);
    setMinVolume(preset.minVolume);
    setActivePreset(preset.label);
  }

  const queryClient = useQueryClient();

  useEffect(() => {
    function handler() {
      queryClient.invalidateQueries({ queryKey: ["scan"] });
    }
    window.addEventListener("mse:refresh", handler);
    return () => window.removeEventListener("mse:refresh", handler);
  }, [queryClient]);
  const { data, isLoading, dataUpdatedAt } = useScan(
    { top, min_price: minPrice, max_price: maxPrice, min_volume: minVolume },
    autoRefresh
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <ScanSearch className="h-5 w-5 text-cyan-400" />
          <h1 className="text-lg font-bold">Momentum Scanner</h1>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
          >
            Filters
          </Button>
          <ScannerToolbar
            onRefresh={() => queryClient.invalidateQueries({ queryKey: ["scan"] })}
            isLoading={isLoading}
            autoRefresh={autoRefresh}
            onAutoRefreshChange={setAutoRefresh}
            dataUpdatedAt={dataUpdatedAt}
            results={data}
          />
        </div>
      </div>

      <BreadthWidget />

      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <Button
            key={p.label}
            variant={activePreset === p.label ? "default" : "outline"}
            size="sm"
            onClick={() => applyPreset(p)}
            className="text-xs"
          >
            {p.label}
          </Button>
        ))}
      </div>

      {showFilters && (
        <div className="flex flex-wrap items-end gap-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="space-y-1">
            <Label className="text-xs text-zinc-400">Top N</Label>
            <Input
              type="number"
              value={top}
              onChange={(e) => setTop(Number(e.target.value) || 20)}
              className="h-8 w-20 bg-zinc-900"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-zinc-400">Min Price</Label>
            <Input
              type="number"
              value={minPrice}
              onChange={(e) => setMinPrice(Number(e.target.value) || 5)}
              className="h-8 w-24 bg-zinc-900"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-zinc-400">Max Price</Label>
            <Input
              type="number"
              value={maxPrice}
              onChange={(e) => setMaxPrice(Number(e.target.value) || 500)}
              className="h-8 w-24 bg-zinc-900"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-zinc-400">Min Volume</Label>
            <Input
              type="number"
              value={minVolume}
              onChange={(e) => setMinVolume(Number(e.target.value) || 500000)}
              className="h-8 w-28 bg-zinc-900"
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setTop(20);
              setMinPrice(5);
              setMaxPrice(500);
              setMinVolume(500000);
            }}
          >
            Reset
          </Button>
        </div>
      )}

      {isLoading && !data ? (
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full bg-zinc-800" />
          ))}
        </div>
      ) : data && data.length > 0 ? (
        <ScannerTable results={data} isWatched={isWatched} onToggleWatch={toggle} />
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">
          No momentum stocks found matching your criteria.
        </div>
      )}
    </div>
  );
}
