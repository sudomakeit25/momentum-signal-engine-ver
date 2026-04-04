"use client";

import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "mse-price-alerts";

export interface PriceAlert {
  symbol: string;
  target: number;
  direction: "above" | "below";
  triggered?: boolean;
}

function load(): PriceAlert[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export function usePriceAlerts() {
  const [alerts, setAlerts] = useState<PriceAlert[]>(load);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  }, [alerts]);

  const addAlert = useCallback((alert: PriceAlert) => {
    setAlerts((prev) => [...prev, alert]);
  }, []);

  const removeAlert = useCallback((symbol: string, target: number) => {
    setAlerts((prev) =>
      prev.filter((a) => !(a.symbol === symbol && a.target === target))
    );
  }, []);

  const checkAlerts = useCallback(
    (prices: Record<string, number>) => {
      const triggered: PriceAlert[] = [];
      setAlerts((prev) =>
        prev.map((a) => {
          const price = prices[a.symbol];
          if (!price || a.triggered) return a;
          const hit =
            (a.direction === "above" && price >= a.target) ||
            (a.direction === "below" && price <= a.target);
          if (hit) {
            triggered.push(a);
            return { ...a, triggered: true };
          }
          return a;
        })
      );
      return triggered;
    },
    []
  );

  const clearTriggered = useCallback(() => {
    setAlerts((prev) => prev.filter((a) => !a.triggered));
  }, []);

  return { alerts, addAlert, removeAlert, checkAlerts, clearTriggered };
}
