// Shared wording for the probability map panel and its live record.

export function fullDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}

export function skillText(s: number | null | undefined): string {
  if (s == null) return "";
  const v = Math.abs(s * 100).toFixed(1);
  return s >= 0 ? `error ${v}% lower than its usual odds` : `error ${v}% higher than its usual odds`;
}

export function verdictTone(v: string | null | undefined): string {
  if (!v) return "text-zinc-400";
  if (v.startsWith("more")) return "text-emerald-400";
  if (v.startsWith("less")) return "text-amber-400";
  return "text-zinc-300";
}
