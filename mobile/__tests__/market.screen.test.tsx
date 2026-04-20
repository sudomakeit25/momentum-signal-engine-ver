import React from "react";
import { renderWithProviders } from "./_helpers";
import MarketScreen from "../app/(tabs)/market";

const BREADTH = {
  total: 100,
  bullish: 62,
  bearish: 28,
  neutral: 10,
  above_ema21: 72,
  bullish_pct: 62.0,
  above_ema21_pct: 72.0,
};

const REGIME = {
  regime: "trending_up",
  description: "SPY in a strong uptrend with healthy breadth.",
  recommendation: { bias: "long", position_size: "full", stop_width: "normal" },
  spy_price: 589.12,
  spy_change_20d: 3.4,
};

const SECTORS = [
  {
    sector: "Semiconductors",
    symbols: 12,
    dp_accumulating: 4,
    dp_distributing: 1,
    of_bullish: 5,
    of_bearish: 1,
    of_unusual_count: 9,
    momentum_count: 6,
    avg_momentum_score: 72.5,
    flow_direction: "inflow",
    flow_strength: 0.68,
  },
];

const SIGNALS = [
  {
    symbol: "NVDA",
    action: "BUY",
    setup_type: "momentum_breakout",
    entry: 200.5,
    target: 215,
    stop_loss: 195,
    confidence: 0.82,
    reason: "",
    rr_ratio: 2.9,
  },
];

function routeFetch(url: string) {
  if (url.includes("/breadth")) return BREADTH;
  if (url.includes("/market/regime")) return REGIME;
  if (url.includes("/sectors/flow")) return SECTORS;
  if (url.includes("/signals")) return SIGNALS;
  return [];
}

describe("MarketScreen", () => {
  beforeEach(() => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(routeFetch(String(url))),
      }),
    );
  });

  it("renders regime, breadth, sector flow, and top signals", async () => {
    const { findByText } = renderWithProviders(<MarketScreen />);
    expect(await findByText(/trending up/i)).toBeTruthy(); // regime
    expect(await findByText(/62\/100/)).toBeTruthy(); // breadth ratio
    expect(await findByText(/Semiconductors/i)).toBeTruthy(); // sector
    expect(await findByText("NVDA")).toBeTruthy(); // signal symbol
    expect(await findByText(/momentum breakout/i)).toBeTruthy();
  });
});
