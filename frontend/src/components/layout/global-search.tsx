"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";

const RECENT_KEY = "mse-recent-instruments";

function saveRecent(sym: string) {
  if (typeof window === "undefined") return;
  try {
    const prev: string[] = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    const next = [sym, ...prev.filter((s) => s !== sym)].slice(0, 12);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* localStorage unavailable — ignore */
  }
}

export function GlobalSearch() {
  const router = useRouter();
  const [value, setValue] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const sym = value.trim().toUpperCase();
    if (!sym) return;
    saveRecent(sym);
    setValue("");
    router.push(`/instrument/${sym}`);
  }

  return (
    <form
      onSubmit={submit}
      className="hidden md:flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/80 px-2 py-1 text-xs focus-within:border-cyan-500/60"
    >
      <Search className="h-3.5 w-3.5 text-zinc-500" />
      <input
        value={value}
        onChange={(e) => setValue(e.target.value.toUpperCase())}
        placeholder="Instrument (e.g. NVDA, AIR.PA)"
        className="w-48 bg-transparent outline-none placeholder:text-zinc-600"
        spellCheck={false}
        autoComplete="off"
      />
      <button
        type="submit"
        disabled={!value.trim()}
        className="rounded bg-cyan-600 px-2 py-0.5 text-[11px] font-semibold text-white transition hover:bg-cyan-500 disabled:opacity-40"
      >
        Open
      </button>
    </form>
  );
}
