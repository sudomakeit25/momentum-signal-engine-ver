import { cn } from "@/lib/utils";
import { SETUP_TYPE_LABELS } from "@/lib/constants";
import type { SignalAction, SetupType } from "@/types/api";

export function SignalChip({
  action,
  setupType,
}: {
  action: SignalAction;
  setupType?: SetupType;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold",
        action === "BUY"
          ? "bg-emerald-500/20 text-emerald-400"
          : "bg-red-500/20 text-red-400"
      )}
    >
      {action}
      {setupType && (
        <span className="font-normal opacity-70">
          {SETUP_TYPE_LABELS[setupType]}
        </span>
      )}
    </span>
  );
}
