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

  // --- Stage 1: Instrument tab endpoints ---
  events: (symbol: string) =>
    request<EventsResponse>(`/instrument/${symbol}/events`),

  insiderTrades: (symbol: string) =>
    request<InsiderTradesResponse>(`/instrument/${symbol}/insider-trades`),

  transcripts: (symbol: string) =>
    request<TranscriptsResponse>(`/instrument/${symbol}/transcripts`),

  transcript: (symbol: string, year: number, quarter: number) =>
    request<TranscriptSummary>(
      `/instrument/${symbol}/transcript/${year}/${quarter}`,
    ),

  multiTf: (symbol: string) =>
    request<MultiTFResponse>(`/multi-tf/${symbol}`),

  fibonacci: (symbol: string) =>
    request<FibonacciResponse>(`/analysis/fibonacci/${symbol}`),

  ichimoku: (symbol: string) =>
    request<IchimokuResponse>(`/analysis/ichimoku/${symbol}`),

  volumeProfile: (symbol: string) =>
    request<VolumeProfileResponse>(`/analysis/volume-profile/${symbol}`),

  shareSignal: (params: {
    symbol: string;
    action: string;
    entry: number;
    target: number;
    stop_loss: number;
    setup_type?: string;
    confidence?: number;
  }) => request<ShareSignalResponse>("/share/signal", params, "POST"),

  // --- Stage 2: Market-wide endpoints ---
  breadth: () => request<BreadthResponse>("/breadth"),
  regime: () => request<RegimeResponse>("/market/regime"),
  sectorFlow: () => request<SectorFlow[]>("/sectors/flow"),
  topSignals: (top = 20) => request<SignalSummary[]>("/signals", { top }),
  darkPoolScan: (top = 10) =>
    request<DarkPoolScanRow[]>("/dark-pool/scan", { top }),
  optionsFlowScan: (top = 10) =>
    request<OptionsFlowScanRow[]>("/options-flow/scan", { top }),
  ipoCalendar: () => request<IpoCalendarResponse>("/market/ipos"),

  intradayPatterns: () =>
    request<{ patterns: IntradayPattern[] }>("/scanner/intraday-patterns"),

  // --- Stage 3: Utility endpoints ---
  alertsHistory: (limit = 100, enrich = false) =>
    request<AlertHistoryItem[]>("/alerts/history", { limit, enrich }),
  journalTrades: () => request<JournalTrade[]>("/journal/trades"),
  journalStats: () => request<JournalStats>("/journal/stats"),
  addTrade: (params: {
    symbol: string;
    side?: string;
    shares: number;
    entry_price: number;
    stop_loss?: number;
    target?: number;
    setup_type?: string;
    notes?: string;
  }) =>
    request<{ status: string }>("/journal/trades", params, "POST"),
  closeTrade: (tradeId: string, exit_price: number) =>
    request<{ status: string; pnl: number }>(
      `/journal/trades/${tradeId}/close`,
      { exit_price },
      "POST",
    ),
  communityFeed: (limit = 50, symbol?: string) =>
    request<CommunityPost[]>("/community/feed", { limit, symbol }),
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

// --- Events ---
export type UpcomingEarnings = {
  date: string;
  eps_estimated: number | null;
  revenue_estimated: number | null;
};
export type RecentEarnings = {
  date: string;
  eps: number | null;
  eps_estimated: number | null;
  revenue: number | null;
  surprise_pct: number | null;
};
export type RecentDividend = {
  date: string;
  dividend: number | null;
  record_date: string | null;
  payment_date: string | null;
};
export type RecentSplit = {
  date: string;
  ratio: string | null;
  numerator: number | null;
  denominator: number | null;
};
export type EventsResponse = {
  symbol: string;
  next_earnings: UpcomingEarnings | null;
  recent_earnings: RecentEarnings[];
  recent_dividends: RecentDividend[];
  recent_splits: RecentSplit[];
};

// --- Insider trades ---
export type InsiderTrade = {
  filing_date: string;
  transaction_date: string;
  reporter_name: string;
  reporter_title: string;
  transaction_type: string;
  shares: number;
  price: number;
  value: number;
  acquired_disposed: string;
  link: string;
};
export type InsiderTradesResponse = {
  symbol: string;
  count: number;
  trades: InsiderTrade[];
};

// --- Transcripts ---
export type TranscriptQuarter = {
  year: number;
  quarter: number;
  date?: string;
};
export type TranscriptsResponse = {
  symbol: string;
  quarters: TranscriptQuarter[];
};
export type TranscriptSummary = {
  symbol?: string;
  quarter?: number;
  year?: number;
  call_date?: string;
  markdown?: string;
  transcript_truncated?: boolean;
  error?: string;
  configure_hint?: string;
};

// --- Multi-TF ---
export type TfResult = {
  label: string;
  trend: string;
  price?: number;
  ema9?: number;
  ema21?: number;
  rsi?: number;
  high_20?: number;
  low_20?: number;
  signals?: Array<{
    action: string;
    setup_type: string;
    entry: number;
    target: number;
    stop_loss: number;
    confidence: number;
    reason: string;
  }>;
  signal_count?: number;
  bars?: number;
  summary: string;
};
export type MultiTFResponse = {
  symbol: string;
  timeframes: Record<string, TfResult>;
  alignment?: string;
  alignment_strength?: number;
  recommendation?: {
    bias?: string;
    confidence?: number;
    notes?: string[];
  };
};

// --- Fibonacci / Ichimoku / Volume profile ---
export type FibonacciResponse = {
  symbol: string;
  trend?: string;
  high?: number;
  low?: number;
  current?: number;
  levels?: Record<string, number>;
  nearest_level?: string;
  nearest_price?: number;
  error?: string;
};

export type IchimokuResponse = {
  symbol: string;
  current?: number;
  tenkan?: number;
  kijun?: number;
  senkou_a?: number | null;
  senkou_b?: number | null;
  cloud_top?: number;
  cloud_bottom?: number;
  signal?: string;
  tk_cross?: string;
  error?: string;
};

export type VolumeProfileBin = {
  price_low: number;
  price_high: number;
  price_mid: number;
  volume: number;
};
export type VolumeProfileResponse = {
  symbol: string;
  current?: number;
  poc?: number;
  value_area_high?: number;
  value_area_low?: number;
  profile?: VolumeProfileBin[];
  error?: string;
};

// --- Share ---
export type ShareSignalResponse = {
  share_id?: string;
  url?: string;
  error?: string;
};

// --- Breadth / regime / sectors ---
export type BreadthResponse = {
  total: number;
  bullish: number;
  bearish: number;
  neutral: number;
  above_ema21: number;
  bullish_pct: number;
  above_ema21_pct: number;
};

export type RegimeResponse = {
  regime: string;
  description?: string;
  confidence_adjustment?: number;
  components?: Record<string, number | string>;
  recommendation?: {
    bias: string;
    position_size: string;
    stop_width: string;
  };
  spy_price?: number;
  spy_change_20d?: number;
};

export type SectorFlow = {
  sector: string;
  symbols: number;
  dp_accumulating: number;
  dp_distributing: number;
  of_bullish: number;
  of_bearish: number;
  of_unusual_count: number;
  momentum_count: number;
  avg_momentum_score: number;
  flow_direction: string;
  flow_strength: number;
};

// --- Dark pool / options flow scans ---
export type DarkPoolScanRow = {
  symbol: string;
  avg_short_pct: number;
  recent_short_pct: number;
  trend: string;
  trend_strength: number;
  price_change_pct: number;
  alert_reasons: string[];
};
export type OptionsFlowScanRow = {
  symbol: string;
  put_call_ratio: number;
  total_call_volume: number;
  total_put_volume: number;
  flow_sentiment: string;
  alert_reasons: string[];
};

// --- Intraday patterns ---
export type IntradayPattern = {
  symbol: string;
  pattern_type:
    | "v_reversal"
    | "inverted_v"
    | "breakdown"
    | "breakout"
    | string;
  action: "BUY" | "SELL" | string;
  trigger_price: number;
  extreme_price: number;
  move_pct: number;
  recovery_pct: number;
  volume_confirmed: boolean;
  detected_at: string;
};

// --- IPOs ---
export type IpoEntry = {
  symbol: string;
  company: string;
  date: string;
  price_range?: string;
  shares?: number;
  exchange?: string;
};
export type IpoCalendarResponse = {
  upcoming: IpoEntry[];
  recent: IpoEntry[];
};

// --- Alerts history ---
export type AlertHistoryItem = {
  symbol: string;
  action: string;
  setup_type: string;
  entry: number;
  target?: number;
  stop_loss?: number;
  confidence?: number;
  dispatched_at?: string;
  channel?: string;
  current_price?: number | null;
  pnl_pct?: number | null;
  pnl_direction?: string | null;
};

// --- Journal ---
export type JournalTrade = {
  id?: string;
  symbol: string;
  side: string;
  shares: number;
  entry_price: number;
  exit_price: number | null;
  stop_loss: number | null;
  target: number | null;
  status: string;
  setup_type: string;
  notes: string;
  entry_date: string;
  exit_date: string | null;
  pnl: number | null;
  r_multiple: number | null;
};
export type JournalStats = {
  total_trades?: number;
  open_trades?: number;
  closed_trades?: number;
  winners?: number;
  losers?: number;
  win_rate?: number;
  avg_r?: number;
  total_pnl?: number;
};

// --- Community ---
export type CommunityComment = {
  user_id: string;
  user_name: string;
  content: string;
  created_at: string;
};
export type CommunityPost = {
  id: string;
  user_id: string;
  user_name: string;
  content: string;
  symbol: string;
  trade_data: Record<string, unknown> | null;
  created_at: string;
  likes: number;
  comments: CommunityComment[];
};
