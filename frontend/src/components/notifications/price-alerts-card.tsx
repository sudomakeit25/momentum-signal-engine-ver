"use client";

import { useEffect, useState } from "react";
import { Target, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface AlertLevel {
  symbol: string;
  price: number;
  side: "above" | "below";
  ref: number;
  added: string;
  hit: { at: string; extreme: number } | null;
}

interface Props {
  apiBase: string;
  keyHeaders: () => Record<string, string>;
  say: (text: string, ok: boolean) => void;
  refused: (res: Response, data: { detail?: string }) => boolean;
}

function money(v: number): string {
  return v >= 1 ? `$${v.toFixed(2)}` : `$${v.toFixed(4)}`;
}

// Price levels for the probability map alerts: Telegram and SMS the first
// time the stock trades there in regular hours, with the map's odds.
export function PriceAlertsCard({ apiBase, keyHeaders, say, refused }: Props) {
  const [levels, setLevels] = useState<AlertLevel[]>([]);
  const [symbol, setSymbol] = useState("CLSK");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    fetch(`${apiBase}/alerts/levels`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setLevels(data?.levels ?? []))
      .catch(() => setLevels([]));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const add = async () => {
    const p = Number(price);
    if (!symbol.trim() || !Number.isFinite(p) || p <= 0) {
      say("Enter a stock symbol and a price.", false);
      return;
    }
    setBusy(true);
    try {
      const q = new URLSearchParams({ symbol: symbol.trim().toUpperCase(), price: String(p) });
      const res = await fetch(`${apiBase}/alerts/levels?${q}`, { method: "POST", headers: keyHeaders() });
      const data = await res.json().catch(() => ({}));
      if (refused(res, data)) return;
      if (!res.ok || !data.ok) {
        say(data.note || data.detail || "Could not add the price alert.", false);
        return;
      }
      say(`Alert set: ${data.level.symbol} ${data.level.side} ${money(data.level.price)}.`, true);
      setPrice("");
      load();
    } finally {
      setBusy(false);
    }
  };

  const remove = async (lvl: AlertLevel) => {
    const q = new URLSearchParams({ symbol: lvl.symbol, price: String(lvl.price) });
    const res = await fetch(`${apiBase}/alerts/levels?${q}`, { method: "DELETE", headers: keyHeaders() });
    const data = await res.json().catch(() => ({}));
    if (refused(res, data)) return;
    say(data.ok ? `Removed ${lvl.symbol} ${money(lvl.price)}.` : data.note || "Could not remove it.", !!data.ok);
    load();
  };

  return (
    <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="flex items-center gap-2">
        <Target className="h-4 w-4 text-violet-400" />
        <h2 className="text-sm font-semibold text-zinc-300">Price alerts</h2>
      </div>
      <p className="text-xs text-zinc-500">
        Telegram and SMS the first time a stock trades at your price in regular hours (checked every minute from
        real-time IEX prices), with the probability map&apos;s odds and how often past touches held. Needs Auto-Alerts on
        and the settings key above.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="Symbol"
          className="h-8 w-24 rounded border border-zinc-700 bg-zinc-950 px-2 text-xs text-zinc-200"
          aria-label="Stock symbol"
        />
        <input
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="Price, e.g. 6.52"
          inputMode="decimal"
          className="h-8 w-32 rounded border border-zinc-700 bg-zinc-950 px-2 text-xs text-zinc-200"
          aria-label="Alert price"
        />
        <Button onClick={add} disabled={busy} variant="outline" size="sm" className="h-8 text-xs">
          {busy ? "Adding..." : "Add alert"}
        </Button>
      </div>
      {levels.length === 0 ? (
        <p className="text-xs text-zinc-600">No price alerts yet.</p>
      ) : (
        <ul className="space-y-1">
          {levels.map((lvl) => (
            <li key={`${lvl.symbol}-${lvl.price}`} className="flex items-center justify-between gap-2 text-xs">
              <span className={cn(lvl.hit ? "text-zinc-500" : "text-zinc-300")}>
                <span className="font-medium">{lvl.symbol}</span> {lvl.side === "above" ? "at or above" : "at or below"}{" "}
                {money(lvl.price)}
                {lvl.hit ? (
                  <span className="text-emerald-400"> · reached {new Date(lvl.hit.at).toLocaleString()}</span>
                ) : (
                  <span className="text-zinc-500"> · waiting (set when it was {money(lvl.ref)})</span>
                )}
              </span>
              <button
                onClick={() => remove(lvl)}
                className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
                aria-label={`Remove ${lvl.symbol} ${money(lvl.price)}`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
