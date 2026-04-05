"use client";

import { Newspaper } from "lucide-react";
import { useNewsFeed } from "@/hooks/use-analytics";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function NewsPage() {
  const { data, isLoading } = useNewsFeed();
  const market = data?.market_sentiment as Record<string, unknown> | undefined;
  const articles = (data?.articles || []) as Record<string, unknown>[];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Newspaper className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">News Sentiment</h1>
      </div>

      {market && (
        <div className="grid grid-cols-4 gap-3">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
            <p className={cn("text-2xl font-bold", market.sentiment === "bullish" ? "text-emerald-400" : market.sentiment === "bearish" ? "text-red-400" : "text-zinc-300")}>
              {String(market.sentiment).toUpperCase()}
            </p>
            <p className="text-xs text-zinc-500">Market Mood</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
            <p className="text-2xl font-bold text-emerald-400">{String(market.bullish)}</p>
            <p className="text-xs text-zinc-500">Bullish</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
            <p className="text-2xl font-bold text-red-400">{String(market.bearish)}</p>
            <p className="text-xs text-zinc-500">Bearish</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
            <p className="text-2xl font-bold text-zinc-400">{String(market.neutral)}</p>
            <p className="text-xs text-zinc-500">Neutral</p>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-16 w-full bg-zinc-800" />)}</div>
      ) : articles.length > 0 ? (
        <div className="space-y-2">
          {articles.map((a, i) => (
            <a key={i} href={String(a.link)} target="_blank" rel="noopener noreferrer" className="block rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 transition-colors hover:border-zinc-700">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <p className="text-sm font-medium text-zinc-200">{String(a.title)}</p>
                  <p className="mt-1 text-xs text-zinc-500 line-clamp-2">{String(a.description)}</p>
                  <div className="mt-2 flex items-center gap-3 text-xs text-zinc-600">
                    <span>{String(a.source)}</span>
                    {(a.symbols as string[])?.length > 0 && <span className="text-cyan-400">{(a.symbols as string[]).join(", ")}</span>}
                  </div>
                </div>
                <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-xs font-medium",
                  a.sentiment === "bullish" ? "bg-emerald-400/10 text-emerald-400" : a.sentiment === "bearish" ? "bg-red-400/10 text-red-400" : "bg-zinc-400/10 text-zinc-400"
                )}>
                  {String(a.sentiment)}
                </span>
              </div>
            </a>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">No news available.</div>
      )}
    </div>
  );
}
