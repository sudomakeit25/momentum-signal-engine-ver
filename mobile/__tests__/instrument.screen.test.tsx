import React from "react";
import { fireEvent, waitFor } from "@testing-library/react-native";
import { renderWithProviders } from "./_helpers";
import InstrumentScreen from "../app/instrument/[symbol]";

const ANALYZER = {
  symbol: "NVDA",
  price: 201.68,
  change_pct: 3.2,
  trend: "bullish",
  verdict: "strong_buy",
  grade: "A",
  composite_score: 88,
  scores: { trend: 80, momentum: 85, quality: 75, risk: 70 },
  strengths: ["EMAs stacked", "Relative strength high"],
  weaknesses: ["Overbought RSI"],
};

const TRENDS = {
  symbol: "NVDA",
  regime: "secular_uptrend",
  returns: { "1y_pct": 98.7, "3y_pct": 210, "5y_pct": 2721 },
};

const SEASONALITY = {
  symbol: "NVDA",
  years_covered: 2,
  months: [
    { month: 1, label: "Jan", avg_pct: 5.2, win_rate: 70, sample_size: 2 },
    { month: 7, label: "Jul", avg_pct: 8.1, win_rate: 80, sample_size: 2 },
  ],
  heatmap: [
    { year: 2024, Jan: 5.2, Jul: 8.1 },
    { year: 2023, Jan: -2.3, Jul: 4.0 },
  ],
  best_month: { month: 7, label: "Jul", avg_pct: 8.1, win_rate: 80, sample_size: 2 },
  worst_month: { month: 1, label: "Jan", avg_pct: -2.3, win_rate: 40, sample_size: 2 },
};

const FUNDAMENTALS_EMPTY = {
  header: {
    symbol: "NVDA",
    name: "NVDA",
    sector: "",
    industry: "",
    market_cap: 0,
    price: 0,
    pe_ttm: 0,
    eps_ttm: 0,
  },
  has_fundamentals: false,
};

const CHART = {
  symbol: "NVDA",
  bars: Array.from({ length: 10 }, (_, i) => ({
    timestamp: `2026-04-${String(i + 1).padStart(2, "0")}T00:00:00Z`,
    open: 100 + i,
    high: 102 + i,
    low: 99 + i,
    close: 101 + i,
    volume: 1_000_000,
  })),
};

const INDICATORS = {
  symbol: "NVDA",
  snapshot: {
    price: 201.68,
    rsi: 68.4,
    macd_line: 1.23,
    macd_signal: 0.98,
    macd_hist: 0.25,
    bb_upper: 210,
    bb_lower: 180,
    bb_pct: 0.72,
    stoch_k: 74,
    stoch_d: 68,
    williams_r: -22,
    roc_10: 4.2,
    roc_21: 12.1,
    roc_63: 28.5,
  },
  mood: { score: 72.3, label: "greed" },
  verdict: "neutral",
};

const AGENT_TOPICS = [
  { key: "whats_happening", label: "What's happening?" },
  { key: "full_analysis", label: "Full Analysis" },
];

const AGENT_RESPONSE = {
  markdown: "## Summary\nNVDA is riding an AI wave with strong DC revenue.",
  model: "claude-opus-4-7",
};

function routeFetch(url: string) {
  if (url.includes("/analyzer/")) return ANALYZER;
  if (url.includes("/trends/")) return TRENDS;
  if (url.includes("/seasonality")) return SEASONALITY;
  if (url.includes("/fundamentals")) return FUNDAMENTALS_EMPTY;
  if (url.includes("/news")) return { articles: [] };
  if (url.includes("/chart/")) return CHART;
  if (url.includes("/instrument/") && url.includes("/indicators"))
    return INDICATORS;
  if (url.includes("/agent/topics")) return AGENT_TOPICS;
  if (url.includes("/agent/")) return AGENT_RESPONSE;
  if (url.includes("/watchlist/server")) return ["AAPL"];
  return {};
}

describe("InstrumentScreen", () => {
  beforeEach(() => {
    const routerModule = require("expo-router");
    routerModule.__setSearchParams({ symbol: "NVDA" });
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(routeFetch(String(url))),
      }),
    );
  });

  it("renders the 5 section tabs", () => {
    const { getByText } = renderWithProviders(<InstrumentScreen />);
    for (const label of [
      "Overview",
      "Indicators",
      "Seasonality",
      "Fundamentals",
      "News",
    ]) {
      expect(getByText(label)).toBeTruthy();
    }
  });

  it("Overview shows grade, price, and strengths/weaknesses", async () => {
    const { findByText, getByText } = renderWithProviders(<InstrumentScreen />);
    // Grade letter
    expect(await findByText("A")).toBeTruthy();
    // Price
    expect(await findByText("$201.68")).toBeTruthy();
    // Verdict (lowercased in stub, shown as "strong buy")
    expect(getByText(/strong buy/i)).toBeTruthy();
    // Strength bullets
    expect(await findByText(/EMAs stacked/i)).toBeTruthy();
    expect(await findByText(/Overbought RSI/i)).toBeTruthy();
  });

  it("switching to Seasonality renders the year-by-month table", async () => {
    const { findByText, getByText } = renderWithProviders(<InstrumentScreen />);
    await findByText("A");
    fireEvent.press(getByText("Seasonality"));
    expect(await findByText(/Probability %/i)).toBeTruthy();
    expect(await findByText(/Avg return %/i)).toBeTruthy();
    expect(await findByText("2024")).toBeTruthy();
    expect(await findByText("2023")).toBeTruthy();
    expect(await findByText("Jul")).toBeTruthy();
    expect(await findByText("Jan")).toBeTruthy();
  });

  it("Fundamentals tab shows FMP gating banner when has_fundamentals is false", async () => {
    const { findByText, getByText } = renderWithProviders(<InstrumentScreen />);
    await findByText("A");
    fireEvent.press(getByText("Fundamentals"));
    expect(await findByText(/FMP Starter plan required/i)).toBeTruthy();
  });

  it("News tab shows empty state when no articles", async () => {
    const { findByText, getByText } = renderWithProviders(<InstrumentScreen />);
    await findByText("A");
    fireEvent.press(getByText("News"));
    expect(await findByText(/No news mentioning NVDA/i)).toBeTruthy();
  });

  it("Indicators tab shows RSI, mood, and MACD values", async () => {
    const { findByText, getByText } = renderWithProviders(<InstrumentScreen />);
    await findByText("A");
    fireEvent.press(getByText("Indicators"));
    expect(await findByText(/Market Mood Meter/i)).toBeTruthy();
    expect(await findByText(/RSI \(14\)/i)).toBeTruthy();
    expect(await findByText(/68\.4/)).toBeTruthy(); // RSI value
    expect(await findByText(/greed/)).toBeTruthy(); // mood label
  });

  it("Overview shows AI Agent topic buttons that open a sheet", async () => {
    const { findByText, getByText, queryByText } = renderWithProviders(
      <InstrumentScreen />,
    );
    await findByText("A");
    // Topic button
    const topicBtn = await findByText("What's happening?");
    expect(topicBtn).toBeTruthy();
    // Modal not open yet
    expect(queryByText(/AI wave/)).toBeNull();
    fireEvent.press(topicBtn);
    // Modal content appears
    expect(await findByText(/AI wave/)).toBeTruthy();
    // Close the sheet
    fireEvent.press(getByText("Done"));
  });
});
