"use client";

import { useState, useEffect, useCallback } from "react";
import { apiPost } from "@/lib/api";

const STORAGE_KEY = "mse-watchlist";

function load(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function syncToServer(symbols: string[]) {
  if (symbols.length === 0) return;
  apiPost("/watchlist/sync", { symbols: symbols.join(",") }).catch(() => {});
}

export function useWatchlist() {
  const [symbols, setSymbols] = useState<string[]>(load);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(symbols));
    syncToServer(symbols);
  }, [symbols]);

  const toggle = useCallback((symbol: string) => {
    setSymbols((prev) =>
      prev.includes(symbol)
        ? prev.filter((s) => s !== symbol)
        : [...prev, symbol]
    );
  }, []);

  const addMany = useCallback((newSymbols: string[]) => {
    setSymbols((prev) => {
      const set = new Set(prev);
      let added = 0;
      for (const s of newSymbols) {
        const sym = s.toUpperCase();
        if (!set.has(sym)) {
          set.add(sym);
          added++;
        }
      }
      return added > 0 ? Array.from(set) : prev;
    });
  }, []);

  const isWatched = useCallback(
    (symbol: string) => symbols.includes(symbol),
    [symbols]
  );

  return { symbols, toggle, addMany, isWatched };
}
