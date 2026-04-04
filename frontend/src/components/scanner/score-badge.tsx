import { cn } from "@/lib/utils";

export function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70
      ? "bg-emerald-500/20 text-emerald-400"
      : score >= 40
        ? "bg-yellow-500/20 text-yellow-400"
        : "bg-zinc-500/20 text-zinc-400";

  return (
    <div className="flex items-center gap-2">
      <span className={cn("rounded px-2 py-0.5 text-xs font-bold", color)}>
        {score.toFixed(0)}
      </span>
      <div className="h-1.5 w-16 rounded-full bg-zinc-800">
        <div
          className={cn(
            "h-full rounded-full",
            score >= 70
              ? "bg-emerald-500"
              : score >= 40
                ? "bg-yellow-500"
                : "bg-zinc-500"
          )}
          style={{ width: `${Math.min(score, 100)}%` }}
        />
      </div>
    </div>
  );
}
