"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";
import { GlobalSearch } from "./global-search";

const TICKER_SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "BTC/USD", "ETH/USD"];

interface TickerItem {
  symbol: string;
  price: number;
  change_pct: number;
}

function useTickerData() {
  return useQuery({
    queryKey: ["ticker-bar"],
    queryFn: async () => {
      const data = await apiFetch<Record<string, unknown>[]>("/scan", { top: 100 });
      const items: TickerItem[] = [];
      for (const sym of TICKER_SYMBOLS) {
        const match = data?.find((d) => d.symbol === sym);
        if (match) {
          items.push({
            symbol: sym,
            price: Number(match.price),
            change_pct: Number(match.change_pct),
          });
        }
      }
      return items;
    },
    refetchInterval: 60_000,
  });
}

export function TickerBar() {
  const { data } = useTickerData();

  return (
    <div className="hidden md:flex items-center gap-4 border-b border-zinc-800/50 bg-zinc-950 px-4 py-1.5 text-[11px]">
      <GlobalSearch />
      <div className="flex flex-1 items-center gap-6 overflow-x-auto scrollbar-none">
        {(data ?? []).map((item) => (
          <div key={item.symbol} className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="font-medium text-zinc-400">{item.symbol}</span>
            <span className="font-mono text-zinc-300">${item.price.toFixed(2)}</span>
            <span className={cn("font-mono", item.change_pct >= 0 ? "text-emerald-400" : "text-red-400")}>
              {item.change_pct >= 0 ? "+" : ""}{item.change_pct.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
