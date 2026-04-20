import React from "react";
import { mockFetchJson, renderWithProviders } from "./_helpers";
import AlertsScreen from "../app/alerts";

describe("AlertsScreen", () => {
  it("renders alert history with enriched P&L", async () => {
    mockFetchJson([
      {
        symbol: "NVDA",
        action: "BUY",
        setup_type: "momentum_breakout",
        entry: 200,
        target: 215,
        stop_loss: 195,
        confidence: 0.8,
        dispatched_at: "2026-04-15T15:30:00",
        channel: "push",
        current_price: 210.5,
        pnl_pct: 5.25,
        pnl_direction: "profit",
      },
    ]);
    const { findByText } = renderWithProviders(<AlertsScreen />);
    expect(await findByText("NVDA")).toBeTruthy();
    expect(await findByText("BUY")).toBeTruthy();
    expect(await findByText(/momentum breakout/i)).toBeTruthy();
    expect(await findByText(/\+5\.25%/)).toBeTruthy();
  });

  it("shows the empty state when no alerts", async () => {
    mockFetchJson([]);
    const { findByText } = renderWithProviders(<AlertsScreen />);
    expect(await findByText(/No alerts have been dispatched/i)).toBeTruthy();
  });
});
