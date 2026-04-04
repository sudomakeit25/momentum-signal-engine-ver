"use client";

import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "mse-watchlist";

function load(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export function useWatchlist() {
  const [symbols, setSymbols] = useState<string[]>(load);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(symbols));
  }, [symbols]);

  const toggle = useCallback((symbol: string) => {
    setSymbols((prev) =>
      prev.includes(symbol)
        ? prev.filter((s) => s !== symbol)
        : [...prev, symbol]
    );
  }, []);

  const isWatched = useCallback(
    (symbol: string) => symbols.includes(symbol),
    [symbols]
  );

  return { symbols, toggle, isWatched };
}
