/**
 * Theme customization.
 * Feature #31.
 */

export const THEMES = {
  dark: {
    name: "Dark",
    bg: "#09090b",
    surface: "#18181b",
    border: "#27272a",
    accent: "#22d3ee",
  },
  midnight: {
    name: "Midnight Blue",
    bg: "#0a0a1a",
    surface: "#12122a",
    border: "#1e1e3a",
    accent: "#818cf8",
  },
  forest: {
    name: "Forest",
    bg: "#0a100e",
    surface: "#121a16",
    border: "#1e2a22",
    accent: "#34d399",
  },
  light: {
    name: "Light",
    bg: "#ffffff",
    surface: "#f4f4f5",
    border: "#e4e4e7",
    accent: "#0891b2",
  },
} as const;

export type ThemeKey = keyof typeof THEMES;

export function applyCustomTheme(theme: ThemeKey): void {
  if (typeof document === "undefined") return;
  const t = THEMES[theme];
  const root = document.documentElement;
  root.style.setProperty("--mse-bg", t.bg);
  root.style.setProperty("--mse-surface", t.surface);
  root.style.setProperty("--mse-border", t.border);
  root.style.setProperty("--mse-accent", t.accent);

  localStorage.setItem("mse-theme", theme);
}

export function loadSavedTheme(): ThemeKey {
  if (typeof localStorage === "undefined") return "dark";
  return (localStorage.getItem("mse-theme") as ThemeKey) || "dark";
}
