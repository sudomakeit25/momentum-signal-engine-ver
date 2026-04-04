"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const SHORTCUTS: Record<string, string> = {
  "1": "/scanner",
  "2": "/chart/SPY",
  "3": "/position-sizer",
  "4": "/backtest",
  "5": "/heatmap",
  "6": "/guide",
};

export function useKeyboardShortcuts() {
  const router = useRouter();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      // Don't fire when typing in inputs
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      // Number keys for navigation
      if (SHORTCUTS[e.key]) {
        e.preventDefault();
        router.push(SHORTCUTS[e.key]);
        return;
      }

      // R = refresh (dispatch custom event)
      if (e.key === "r" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("mse:refresh"));
        return;
      }

      // ? = show shortcuts help
      if (e.key === "?") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("mse:show-shortcuts"));
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [router]);
}
