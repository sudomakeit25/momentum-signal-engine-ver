import { api, API_BASE } from "../src/lib/api";

describe("API client", () => {
  beforeEach(() => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn();
  });

  const mockFetch = () => (global as unknown as { fetch: jest.Mock }).fetch;

  it("reads API_BASE from expo-constants extra", () => {
    expect(API_BASE).toBe("https://example-backend.test");
  });

  it("scan() hits /scan with the right query param", async () => {
    mockFetch().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    await api.scan(25);
    const url = mockFetch().mock.calls[0][0] as string;
    expect(url).toBe("https://example-backend.test/scan?top=25");
  });

  it("analyzer() hits /analyzer/:symbol", async () => {
    mockFetch().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          symbol: "NVDA",
          price: 201,
          change_pct: 1,
          trend: "bullish",
          verdict: "buy",
          grade: "B",
          composite_score: 72,
          scores: { trend: 80, momentum: 70, quality: 65, risk: 75 },
        }),
    });
    const r = await api.analyzer("NVDA");
    expect(mockFetch().mock.calls[0][0]).toBe(
      "https://example-backend.test/analyzer/NVDA",
    );
    expect(r.symbol).toBe("NVDA");
    expect(r.grade).toBe("B");
  });

  it("throws on non-2xx", async () => {
    mockFetch().mockResolvedValue({ ok: false, status: 500, json: () => ({}) });
    await expect(api.trends("FAIL")).rejects.toThrow(/500/);
  });

  it("seasonality error payload is passed through", async () => {
    mockFetch().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({ symbol: "X", error: "insufficient history" }),
    });
    const r = await api.seasonality("X");
    expect(r.error).toBe("insufficient history");
    expect(r.months).toBeUndefined();
  });
});
