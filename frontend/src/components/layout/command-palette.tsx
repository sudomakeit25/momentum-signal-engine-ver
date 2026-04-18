"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search, X } from "lucide-react";

const POPULAR_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "SPY", "QQQ"];

const PAGES = [
  { href: "/scanner", label: "Scanner" },
  { href: "/custom-screener", label: "Custom Screener" },
  { href: "/signals-advanced", label: "Advanced Signals" },
  { href: "/smart-money", label: "Smart Money" },
  { href: "/dark-pool", label: "Dark Pool" },
  { href: "/options-flow", label: "Options Flow" },
  { href: "/earnings", label: "Earnings" },
  { href: "/news", label: "News Sentiment" },
  { href: "/market-regime", label: "Market Regime" },
  { href: "/trading", label: "Paper Trading" },
  { href: "/journal", label: "Trade Journal" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/community", label: "Community" },
  { href: "/technical", label: "Technical Tools" },
  { href: "/portfolio-analytics", label: "Portfolio Analytics" },
  { href: "/multi-tf", label: "Multi-Timeframe" },
  { href: "/correlations", label: "Correlations" },
  { href: "/sector-flow", label: "Sector Flow" },
  { href: "/options-builder", label: "Options Builder" },
  { href: "/screener-presets", label: "Preset Screeners" },
  { href: "/stock-screener", label: "Stock Screener (Yahoo)" },
  { href: "/holdings", label: "My Holdings" },
  { href: "/instrument", label: "Instrument Search" },
  { href: "/sector-map", label: "Sector Map" },
  { href: "/rankings", label: "Industry Rankings" },
  { href: "/cot", label: "COT Reports" },
  { href: "/analyzer", label: "Stock Analyzer" },
  { href: "/trends", label: "Multi-Year Trends" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  function navigate(href: string) {
    router.push(href);
    setOpen(false);
    setQuery("");
  }

  const q = query.trim().toUpperCase();
  const isSymbol = /^[A-Z]{1,5}$/.test(q);

  const filteredPages = query
    ? PAGES.filter((p) => p.label.toLowerCase().includes(query.toLowerCase()))
    : PAGES.slice(0, 8);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[20vh]">
      <div className="fixed inset-0 bg-black/60" onClick={() => setOpen(false)} />
      <div className="relative z-10 w-full max-w-md rounded-lg border border-zinc-700 bg-zinc-900 shadow-2xl">
        <div className="flex items-center gap-3 border-b border-zinc-800 px-4 py-3">
          <Search className="h-4 w-4 text-zinc-500" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && isSymbol) navigate(`/chart/${q}`);
            }}
            placeholder="Search symbols or pages..."
            className="flex-1 bg-transparent text-sm text-zinc-200 placeholder-zinc-600 outline-none"
          />
          <button onClick={() => setOpen(false)} className="text-zinc-600 hover:text-zinc-400">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-72 overflow-y-auto p-2">
          {/* Symbol match */}
          {isSymbol && (
            <>
              <button
                onClick={() => navigate(`/instrument/${q}`)}
                className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-cyan-400 hover:bg-zinc-800"
              >
                <span className="font-mono font-bold">{q}</span>
                <span className="text-xs text-zinc-500">Instrument overview</span>
              </button>
              <button
                onClick={() => navigate(`/chart/${q}`)}
                className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-cyan-400 hover:bg-zinc-800"
              >
                <span className="font-mono font-bold">{q}</span>
                <span className="text-xs text-zinc-500">Open chart</span>
              </button>
            </>
          )}

          {/* Popular symbols when empty */}
          {!query && (
            <div className="mb-2">
              <p className="px-3 py-1 text-[10px] font-semibold uppercase text-zinc-600">Popular</p>
              <div className="flex flex-wrap gap-1 px-3 py-1">
                {POPULAR_SYMBOLS.map((sym) => (
                  <button
                    key={sym}
                    onClick={() => navigate(`/chart/${sym}`)}
                    className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-cyan-400 hover:bg-zinc-700"
                  >
                    {sym}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Pages */}
          <p className="px-3 py-1 text-[10px] font-semibold uppercase text-zinc-600">Pages</p>
          {filteredPages.map((page) => (
            <button
              key={page.href}
              onClick={() => navigate(page.href)}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
            >
              {page.label}
            </button>
          ))}
        </div>

        <div className="border-t border-zinc-800 px-4 py-2 text-[10px] text-zinc-600">
          Type a symbol to open chart. Press Enter or click a page.
        </div>
      </div>
    </div>
  );
}
