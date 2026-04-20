import React from "react";
import { fireEvent, waitFor } from "@testing-library/react-native";
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

  it("tapping the remove button drops the symbol optimistically", async () => {
    // Start with three symbols; after POST, watchlist fetch returns two
    let state = ["AAPL", "NVDA", "RKLB"];
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn(
      (_url: string, init?: { method?: string }) => {
        if (init?.method === "POST") {
          state = state.filter((s) => s !== "NVDA");
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve({ status: "saved", symbols: state }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(state),
        });
      },
    );
    const { findByText, getAllByText, queryByText } = renderWithProviders(
      <WatchlistScreen />,
    );
    await findByText("NVDA");
    // There's one ✕ per row; press the second one (next to NVDA)
    const removes = getAllByText("✕");
    expect(removes.length).toBe(3);
    fireEvent.press(removes[1]);
    await waitFor(() => expect(queryByText("NVDA")).toBeNull());
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
