"use client";

import { cn } from "@/lib/utils";

export function ConvictionBadge({ score }: { score: number }) {
  const color =
    score >= 70
      ? "text-emerald-400 bg-emerald-400/10 border-emerald-400/20"
      : score >= 50
        ? "text-amber-400 bg-amber-400/10 border-amber-400/20"
        : score >= 30
          ? "text-orange-400 bg-orange-400/10 border-orange-400/20"
          : "text-zinc-400 bg-zinc-400/10 border-zinc-400/20";

  const label =
    score >= 70
      ? "High"
      : score >= 50
        ? "Medium"
        : score >= 30
          ? "Low"
          : "Weak";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        color
      )}
    >
      <span className="font-mono">{score.toFixed(0)}</span>
      <span className="text-[10px] opacity-70">{label}</span>
    </span>
  );
}
