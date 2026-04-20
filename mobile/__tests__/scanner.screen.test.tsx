import React from "react";
import { waitFor } from "@testing-library/react-native";
import { mockFetchJson, renderWithProviders } from "./_helpers";
import ScannerScreen from "../app/(tabs)/index";

const SAMPLE = [
  {
    symbol: "NVDA",
    price: 201.68,
    change_pct: 3.2,
    volume: 42000000,
    avg_volume: 40000000,
    relative_strength: 1.12,
    score: 88,
    setup_types: ["breakout", "ema_stack"],
    signals: [],
  },
  {
    symbol: "RKLB",
    price: 85.13,
    change_pct: -1.4,
    volume: 10000000,
    avg_volume: 8000000,
    relative_strength: 1.05,
    score: 74,
    setup_types: ["momentum"],
    signals: [],
  },
];

describe("ScannerScreen", () => {
  it("shows loading then renders scan rows with score and setups", async () => {
    mockFetchJson(SAMPLE);
    const { getByText, findByText } = renderWithProviders(<ScannerScreen />);
    expect(getByText("Momentum Scanner")).toBeTruthy();

    // Symbols appear once data arrives
    expect(await findByText("NVDA")).toBeTruthy();
    expect(await findByText("RKLB")).toBeTruthy();

    // Setup labels appear
    expect(getByText(/breakout/)).toBeTruthy();

    // Scores rendered (NVDA = 88, RKLB = 74)
    expect(getByText("88")).toBeTruthy();
    expect(getByText("74")).toBeTruthy();
  });

  it("renders positive and negative change colors via the text label", async () => {
    mockFetchJson(SAMPLE);
    const { findByText } = renderWithProviders(<ScannerScreen />);
    const positive = await findByText("+3.20%");
    expect(positive).toBeTruthy();
    const negative = await findByText("-1.40%");
    expect(negative).toBeTruthy();
  });

  it("surfaces error state when the backend fails", async () => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest
      .fn()
      .mockResolvedValue({ ok: false, status: 500, json: () => ({}) });
    const { findByText } = renderWithProviders(<ScannerScreen />);
    // Our API client throws "API error 500: /scan"; screen shows that text.
    expect(await findByText(/API error 500/)).toBeTruthy();
  });
});
