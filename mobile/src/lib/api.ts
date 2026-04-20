// Thin REST client pointed at the production MSE backend. The base URL is
// baked into app.json under `expo.extra.apiBase` so we can override per
// build (EAS env) without changing code.

import Constants from "expo-constants";

const DEFAULT = "https://momentum-signal-engine.onrender.com";
export const API_BASE: string =
  (Constants.expoConfig?.extra?.apiBase as string) || DEFAULT;

async function request<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
  method: "GET" | "POST" = "GET",
): Promise<T> {
  const url = new URL(path, API_BASE);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    }
  }
  const resp = await fetch(url.toString(), { method });
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}: ${path}`);
  }
  return (await resp.json()) as T;
}

export const api = {
  scan: (top = 30) =>
    request<ScanRow[]>("/scan", { top }),

  analyzer: (symbol: string) =>
    request<AnalyzerResponse>(`/analyzer/${symbol}`),

  trends: (symbol: string) =>
    request<TrendsResponse>(`/trends/${symbol}`),

  seasonality: (symbol: string) =>
    request<SeasonalityResponse>(`/instrument/${symbol}/seasonality`),

  fundamentals: (symbol: string) =>
    request<FundamentalsResponse>(`/instrument/${symbol}/fundamentals`),

  news: (symbol: string) =>
    request<NewsResponse>(`/instrument/${symbol}/news`),

  watchlist: () => request<string[]>("/watchlist/server"),

  saveWatchlist: (symbols: string[]) =>
    request<{ status: string; symbols: string[] }>(
      "/watchlist/server",
      { symbols: symbols.join(",") },
      "POST",
    ),

  chart: (symbol: string, days = 180) =>
    request<ChartResponse>(`/chart/${symbol}`, { days }),

  indicators: (symbol: string) =>
    request<IndicatorsResponse>(`/instrument/${symbol}/indicators`),

  agentTopics: () => request<AgentTopic[]>("/agent/topics"),

  agent: (symbol: string, topic: string) =>
    request<AgentResponse>(`/instrument/${symbol}/agent/${topic}`),
};

export type SignalSummary = {
  symbol: string;
  action: "BUY" | "SELL" | string;
  setup_type: string;
  entry: number;
  target?: number;
  stop_loss?: number;
  confidence: number;
  reason?: string;
  rr_ratio?: number;
};

export type ScanRow = {
  symbol: string;
  price: number;
  change_pct: number;
  volume: number;
  avg_volume: number;
  relative_strength: number;
  score: number;
  setup_types: string[];
  signals: SignalSummary[];
};

export type AnalyzerResponse = {
  symbol: string;
  price: number;
  change_pct: number;
  trend: string;
  verdict: string;
  grade: string;
  composite_score: number;
  scores: {
    trend: number;
    momentum: number;
    quality: number;
    risk: number;
  };
  indicators?: {
    rsi: number;
    relative_strength: number;
    atr_pct: number;
  };
  range_52w?: {
    high: number;
    low: number;
    pct_off_high: number;
  };
  strengths?: string[];
  weaknesses?: string[];
  error?: string;
};

export type TrendsResponse = {
  symbol: string;
  regime: string;
  returns?: {
    "1y_pct": number | null;
    "3y_pct": number | null;
    "5y_pct": number | null;
  };
  error?: string;
};

export type SeasonalityMonth = {
  month: number;
  label: string;
  avg_pct: number | null;
  win_rate: number | null;
  sample_size: number;
};

export type SeasonalityHeatmapRow = {
  year: number;
} & Record<string, number | undefined>;

export type SeasonalityResponse = {
  symbol: string;
  years_covered?: number;
  months?: SeasonalityMonth[];
  heatmap?: SeasonalityHeatmapRow[];
  best_month?: SeasonalityMonth;
  worst_month?: SeasonalityMonth;
  error?: string;
};

export type FundamentalsResponse = {
  header?: {
    symbol: string;
    name: string;
    sector: string;
    industry: string;
    market_cap: number;
    price: number;
    pe_ttm: number;
    eps_ttm: number;
  };
  has_fundamentals?: boolean;
  error?: string;
};

export type NewsArticle = {
  source: string;
  title: string;
  description: string;
  link: string;
  pub_date: string;
  sentiment_score: number;
  sentiment: string;
};

export type NewsResponse = {
  symbol: string;
  articles: NewsArticle[];
};

export type ChartBar = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema9?: number | null;
  ema21?: number | null;
  ema50?: number | null;
  ema200?: number | null;
};

export type ChartResponse = {
  symbol: string;
  bars: ChartBar[];
};

export type IndicatorSnapshot = {
  price: number;
  rsi: number | null;
  macd_line: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  bb_pct: number | null;
  stoch_k: number | null;
  stoch_d: number | null;
  williams_r: number | null;
  roc_10: number | null;
  roc_21: number | null;
  roc_63: number | null;
};

export type MoodReading = {
  score: number | null;
  label: string;
};

export type IndicatorsResponse = {
  symbol: string;
  snapshot?: IndicatorSnapshot;
  mood?: MoodReading;
  verdict?: string;
  error?: string;
};

export type AgentTopic = { key: string; label: string };

export type AgentResponse = {
  markdown?: string;
  usage?: { input_tokens: number; output_tokens: number };
  model?: string;
  error?: string;
};
