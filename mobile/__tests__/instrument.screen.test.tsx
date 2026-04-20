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
  years_covered: 10,
  months: [
    { month: 1, label: "Jan", avg_pct: 5.2, win_rate: 70, sample_size: 10 },
    { month: 7, label: "Jul", avg_pct: 8.1, win_rate: 80, sample_size: 10 },
  ],
  best_month: { month: 7, label: "Jul", avg_pct: 8.1, win_rate: 80, sample_size: 10 },
  worst_month: { month: 1, label: "Jan", avg_pct: -2.3, win_rate: 40, sample_size: 10 },
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

function routeFetch(url: string) {
  if (url.includes("/analyzer/")) return ANALYZER;
  if (url.includes("/trends/")) return TRENDS;
  if (url.includes("/seasonality")) return SEASONALITY;
  if (url.includes("/fundamentals")) return FUNDAMENTALS_EMPTY;
  if (url.includes("/news")) return { articles: [] };
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

  it("renders the 4 section tabs", () => {
    const { getByText } = renderWithProviders(<InstrumentScreen />);
    for (const label of ["Overview", "Seasonality", "Fundamentals", "News"]) {
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

  it("switching to Seasonality renders month rows", async () => {
    const { findByText, getByText } = renderWithProviders(<InstrumentScreen />);
    // Wait for Overview to load first
    await findByText("A");
    fireEvent.press(getByText("Seasonality"));
    expect(await findByText(/Average Return by Month/i)).toBeTruthy();
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
});
