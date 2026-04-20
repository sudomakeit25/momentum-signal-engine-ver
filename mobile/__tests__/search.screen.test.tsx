import React from "react";
import { fireEvent } from "@testing-library/react-native";
import { renderWithProviders } from "./_helpers";
import SearchScreen from "../app/(tabs)/search";
import { router } from "expo-router";

describe("SearchScreen", () => {
  beforeEach(() => {
    (router.push as jest.Mock).mockClear();
  });

  it("renders popular, forex, commodities, and indices sections", () => {
    const { getByText } = renderWithProviders(<SearchScreen />);
    expect(getByText("POPULAR")).toBeTruthy();
    expect(getByText("FOREX")).toBeTruthy();
    expect(getByText("COMMODITIES")).toBeTruthy();
    expect(getByText("INDICES")).toBeTruthy();

    // Some representative chips
    expect(getByText("AAPL")).toBeTruthy();
    expect(getByText("EURUSD")).toBeTruthy();
    expect(getByText("GCUSD")).toBeTruthy();
    expect(getByText("^GSPC")).toBeTruthy();
  });

  it("typing a ticker and pressing Open navigates to /instrument/:symbol", () => {
    const { getByPlaceholderText, getByText } = renderWithProviders(
      <SearchScreen />,
    );
    const input = getByPlaceholderText("Ticker (e.g. NVDA, EURUSD)");
    fireEvent.changeText(input, "nvda");
    fireEvent.press(getByText("Open"));

    expect(router.push).toHaveBeenCalledWith(
      `/instrument/${encodeURIComponent("NVDA")}`,
    );
  });

  it("empty input does nothing", () => {
    const { getByText } = renderWithProviders(<SearchScreen />);
    fireEvent.press(getByText("Open"));
    expect(router.push).not.toHaveBeenCalled();
  });

  it("tapping a popular chip navigates to that instrument", () => {
    const { getByText } = renderWithProviders(<SearchScreen />);
    fireEvent.press(getByText("NVDA"));
    expect(router.push).toHaveBeenCalledWith(
      `/instrument/${encodeURIComponent("NVDA")}`,
    );
  });
});
