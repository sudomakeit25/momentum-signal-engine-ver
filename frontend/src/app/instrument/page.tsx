"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Search, Rocket } from "lucide-react";

const POPULAR = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
  "RKLB", "MU", "WDC", "SNDK", "AVGO", "INTC", "SPY", "QQQ",
  "LLY", "UNH", "JPM", "V", "BAC", "XOM", "COST",
];

const RECENT_KEY = "mse-recent-instruments";

function loadRecents(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveRecent(sym: string) {
  if (typeof window === "undefined") return;
  const prev = loadRecents().filter((s) => s !== sym);
  const next = [sym, ...prev].slice(0, 12);
  localStorage.setItem(RECENT_KEY, JSON.stringify(next));
}

export default function InstrumentSearchPage() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [recents, setRecents] = useState<string[]>(() => loadRecents());

  function go(sym: string) {
    const clean = sym.trim().toUpperCase();
    if (!clean) return;
    saveRecent(clean);
    setRecents(loadRecents());
    router.push(`/instrument/${clean}`);
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div className="flex items-center gap-3">
        <Rocket className="h-5 w-5 text-cyan-400" />
        <div>
          <h1 className="text-lg font-bold">Instrument Search</h1>
          <p className="text-xs text-zinc-500">
            Open the overview for any US ticker or international symbol
            (e.g. AIR.PA, BA.L, RHM.DE).
          </p>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          go(value);
        }}
        className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 focus-within:border-cyan-500"
      >
        <Search className="h-4 w-4 text-zinc-500" />
        <input
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value.toUpperCase())}
          placeholder="Ticker (e.g. NVDA, RKLB, AIR.PA)"
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-zinc-600"
        />
        <button
          type="submit"
          disabled={!value.trim()}
          className="rounded-md bg-cyan-600 px-3 py-1 text-xs font-semibold text-white transition hover:bg-cyan-500 disabled:opacity-50"
        >
          Open
        </button>
      </form>

      {recents.length > 0 && (
        <div>
          <div className="mb-2 text-[10px] font-semibold uppercase text-zinc-500">
            Recent
          </div>
          <div className="flex flex-wrap gap-1.5">
            {recents.map((sym) => (
              <Link
                key={sym}
                href={`/instrument/${sym}`}
                onClick={() => saveRecent(sym)}
                className="rounded-md border border-cyan-500/40 bg-cyan-950/40 px-2 py-1 text-xs font-mono text-cyan-300 hover:border-cyan-500 hover:bg-cyan-900/60"
              >
                {sym}
              </Link>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="mb-2 text-[10px] font-semibold uppercase text-zinc-500">
          Popular
        </div>
        <div className="flex flex-wrap gap-1.5">
          {POPULAR.map((sym) => (
            <Link
              key={sym}
              href={`/instrument/${sym}`}
              onClick={() => saveRecent(sym)}
              className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs font-mono text-zinc-300 hover:border-cyan-500/60 hover:text-cyan-300"
            >
              {sym}
            </Link>
          ))}
        </div>
      </div>

      <p className="text-[10px] text-zinc-500">
        Tip: Cmd-K / Ctrl-K from anywhere opens a quick ticker search.
      </p>
    </div>
  );
}
