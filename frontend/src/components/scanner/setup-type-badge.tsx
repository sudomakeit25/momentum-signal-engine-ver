import { cn } from "@/lib/utils";
import { SETUP_TYPE_COLORS, SETUP_TYPE_LABELS } from "@/lib/constants";
import type { SetupType } from "@/types/api";

export function SetupTypeBadge({ type }: { type: SetupType }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium",
        SETUP_TYPE_COLORS[type]
      )}
    >
      {SETUP_TYPE_LABELS[type]}
    </span>
  );
}
