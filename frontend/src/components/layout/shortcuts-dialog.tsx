"use client";

import { useEffect, useState } from "react";

const SHORTCUTS = [
  { key: "1", action: "Go to Scanner" },
  { key: "2", action: "Go to Charts" },
  { key: "3", action: "Go to Position Sizer" },
  { key: "4", action: "Go to Backtest" },
  { key: "5", action: "Go to Heatmap" },
  { key: "6", action: "Go to Guide" },
  { key: "R", action: "Refresh data" },
  { key: "?", action: "Show this help" },
];

export function ShortcutsDialog() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function handler() {
      setOpen((v) => !v);
    }
    window.addEventListener("mse:show-shortcuts", handler);
    return () => window.removeEventListener("mse:show-shortcuts", handler);
  }, []);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60" onClick={() => setOpen(false)}>
      <div
        className="w-80 rounded-lg border border-zinc-700 bg-zinc-900 p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-sm font-bold text-zinc-100">Keyboard Shortcuts</h2>
        <div className="space-y-2">
          {SHORTCUTS.map((s) => (
            <div key={s.key} className="flex items-center justify-between">
              <span className="text-sm text-zinc-400">{s.action}</span>
              <kbd className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-xs text-zinc-300">
                {s.key}
              </kbd>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-zinc-500">Press Esc or click outside to close</p>
      </div>
    </div>
  );
}
