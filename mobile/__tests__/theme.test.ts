import { colors, spacing, radius, fontSize } from "../src/lib/theme";

describe("theme tokens", () => {
  it("exposes a full dark-theme color palette", () => {
    expect(colors.bg).toMatch(/^#/);
    expect(colors.primary).toBe("#22d3ee"); // cyan-400 to match manifest theme_color
    expect(colors.bullish).toBe("#34d399");
    expect(colors.bearish).toBe("#f87171");
  });

  it("spacing scale is monotonic", () => {
    expect(spacing.xs).toBeLessThan(spacing.sm);
    expect(spacing.sm).toBeLessThan(spacing.md);
    expect(spacing.md).toBeLessThan(spacing.lg);
    expect(spacing.lg).toBeLessThan(spacing.xl);
    expect(spacing.xl).toBeLessThan(spacing.xxl);
  });

  it("font sizes and radii are positive numbers", () => {
    for (const v of Object.values(fontSize)) expect(v).toBeGreaterThan(0);
    for (const v of Object.values(radius)) expect(v).toBeGreaterThan(0);
  });
});
