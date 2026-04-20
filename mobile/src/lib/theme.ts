// Minimal design tokens that mirror the web app's dark palette
// (zinc + cyan). Used across every screen so we can swap colors
// in one place later if we introduce a light theme.

export const colors = {
  bg: "#09090b",          // zinc-950
  bgElevated: "#18181b",  // zinc-900
  bgCard: "#27272a",      // zinc-800
  border: "#3f3f46",      // zinc-700
  borderSubtle: "#27272a",
  text: "#fafafa",        // zinc-50
  textMuted: "#a1a1aa",   // zinc-400
  textDim: "#71717a",     // zinc-500
  primary: "#22d3ee",     // cyan-400
  primaryDark: "#06b6d4", // cyan-500
  bullish: "#34d399",     // emerald-400
  bearish: "#f87171",     // red-400
  amber: "#f59e0b",
  indigo: "#a78bfa",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 4,
  md: 8,
  lg: 12,
} as const;

export const fontSize = {
  xs: 10,
  sm: 12,
  md: 14,
  lg: 16,
  xl: 20,
  xxl: 28,
} as const;
