"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Share2, Activity } from "lucide-react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export default function SharedSignalPage() {
  const params = useParams();
  const shareId = params.id as string;

  const { data, isLoading } = useQuery({
    queryKey: ["shared-signal", shareId],
    queryFn: () => apiFetch<Record<string, unknown>>(`/share/${shareId}`),
    enabled: !!shareId,
  });

  const signal = data?.signal as Record<string, unknown> | undefined;

  return (
    <div className="mx-auto max-w-lg space-y-4 pt-8">
      <div className="flex items-center gap-3">
        <Share2 className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Shared Signal</h1>
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full bg-zinc-800" />
      ) : signal ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link href={`/chart/${signal.symbol}`} className="text-2xl font-bold text-cyan-400 hover:underline">
                {String(signal.symbol)}
              </Link>
              <span className={cn("rounded-full px-3 py-1 text-sm font-bold",
                signal.action === "BUY" ? "bg-emerald-400/10 text-emerald-400" : "bg-red-400/10 text-red-400"
              )}>
                {String(signal.action)}
              </span>
            </div>
            <span className="text-xs text-zinc-500">{String(data?.views || 0)} views</span>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="text-center"><p className="text-lg font-bold text-zinc-200">${Number(signal.entry).toFixed(2)}</p><p className="text-xs text-zinc-500">Entry</p></div>
            <div className="text-center"><p className="text-lg font-bold text-emerald-400">${Number(signal.target).toFixed(2)}</p><p className="text-xs text-zinc-500">Target</p></div>
            <div className="text-center"><p className="text-lg font-bold text-red-400">${Number(signal.stop_loss).toFixed(2)}</p><p className="text-xs text-zinc-500">Stop Loss</p></div>
          </div>

          {String(signal.setup_type) && (
            <div className="text-center"><span className="rounded-full bg-zinc-800 px-3 py-1 text-xs text-zinc-400">{String(signal.setup_type)}</span></div>
          )}

          <div className="flex items-center justify-between text-xs text-zinc-600">
            <span>Shared by {String(data?.user_name || "Anonymous")}</span>
            <span>{data?.created_at ? new Date(String(data.created_at)).toLocaleDateString() : ""}</span>
          </div>

          <div className="flex justify-center">
            <Link href={`/chart/${signal.symbol}`} className="text-sm text-cyan-400 hover:underline">View Full Chart</Link>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">Signal not found or has been removed.</div>
      )}

      <div className="text-center">
        <Link href="/scanner" className="flex items-center justify-center gap-2 text-sm text-zinc-500 hover:text-zinc-300">
          <Activity className="h-4 w-4" />
          Momentum Signal Engine
        </Link>
      </div>
    </div>
  );
}
