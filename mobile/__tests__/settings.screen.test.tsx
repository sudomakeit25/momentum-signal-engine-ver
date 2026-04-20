import React from "react";
import { renderWithProviders, mockFetchJson } from "./_helpers";
import SettingsScreen from "../app/(tabs)/settings";

describe("SettingsScreen", () => {
  beforeEach(() => {
    // Backend registration POST — return success so the push flow lands on
    // 'registered' rather than erroring out. Do NOT jest.resetModules here:
    // that would reset React itself and break the test-renderer.
    mockFetchJson({ status: "registered" });
  });

  it("shows version and backend sections", async () => {
    const { getByText, findByText } = renderWithProviders(<SettingsScreen />);
    expect(getByText("ABOUT")).toBeTruthy();
    expect(getByText("LINKS")).toBeTruthy();
    expect(getByText("NOTIFICATIONS")).toBeTruthy();
    expect(getByText("Version")).toBeTruthy();
    expect(getByText("0.1.0")).toBeTruthy();
    expect(getByText("Backend")).toBeTruthy();
    expect(getByText(/example-backend.test/)).toBeTruthy();

    // Push status eventually settles to "Registered ✓" (mocks grant permission).
    expect(await findByText(/Registered/i)).toBeTruthy();
  });
});
