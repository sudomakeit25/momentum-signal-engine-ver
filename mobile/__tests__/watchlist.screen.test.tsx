import React from "react";
import { mockFetchJson, renderWithProviders } from "./_helpers";
import WatchlistScreen from "../app/(tabs)/watchlist";

describe("WatchlistScreen", () => {
  it("renders symbols from /watchlist/server", async () => {
    mockFetchJson(["AAPL", "NVDA", "RKLB"]);
    const { findByText } = renderWithProviders(<WatchlistScreen />);
    expect(await findByText("AAPL")).toBeTruthy();
    expect(await findByText("NVDA")).toBeTruthy();
    expect(await findByText("RKLB")).toBeTruthy();
  });

  it("shows empty state when watchlist is empty", async () => {
    mockFetchJson([]);
    const { findByText } = renderWithProviders(<WatchlistScreen />);
    expect(
      await findByText(/No symbols watched yet/i),
    ).toBeTruthy();
  });

  it("shows error state on backend failure", async () => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest
      .fn()
      .mockResolvedValue({ ok: false, status: 500, json: () => ({}) });
    const { findByText } = renderWithProviders(<WatchlistScreen />);
    expect(await findByText(/API error 500/i)).toBeTruthy();
  });
});
