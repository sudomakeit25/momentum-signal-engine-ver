export type SignalAction = "BUY" | "SELL";

export type SetupType =
  | "ema_crossover"
  | "breakout"
  | "rsi_pullback"
  | "vwap_reclaim"
  | "flag"
  | "flat_base"
  | "tight_consolidation"
  | "gap_up";

export interface Signal {
  symbol: string;
  action: SignalAction;
  setup_type: SetupType;
  reason: string;
  entry: number;
  stop_loss: number;
  target: number;
  rr_ratio: number;
  confidence: number;
  timestamp: string;
}

export interface ScanResult {
  symbol: string;
  price: number;
  change_pct: number;
  volume: number;
  avg_volume: number;
  relative_strength: number;
  score: number;
  signals: Signal[];
  setup_types: SetupType[];
}

export interface PositionSize {
  symbol: string;
  shares: number;
  entry_price: number;
  stop_loss: number;
  target: number;
  dollar_risk: number;
  position_value: number;
  rr_ratio: number;
}

export interface BacktestTrade {
  symbol: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  shares: number;
  pnl: number;
  return_pct: number;
}

export interface BacktestResult {
  strategy: string;
  start_date: string;
  end_date: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  avg_rr: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  trades: BacktestTrade[];
}

export interface ChartBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema9: number | null;
  ema21: number | null;
  ema50: number | null;
  ema200: number | null;
  rsi: number | null;
  macd_line: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  atr: number | null;
  volume_sma20: number | null;
  vwap: number | null;
  rs_vs_spy: number | null;
}

export interface SupportResistanceLevel {
  price: number;
  strength: number;
  touches: number;
  zone_top: number;
  zone_bottom: number;
  level_type: "support" | "resistance";
}

export interface TrendLine {
  start_time: string;
  start_price: number;
  end_time: string;
  end_price: number;
  touches: number;
  trend_type: "uptrend" | "downtrend";
  projection: Array<{ time: string; price: number }>;
}

export interface ChartPattern {
  pattern_type: string;
  confidence: number;
  target_price: number | null;
  boundary_points: Array<{ time: string; price: number }>;
  description: string;
  bias: "bullish" | "bearish" | "neutral";
}

export interface PriceProjection {
  price: number;
  confidence: number;
  reason: string;
  projection_type: "bullish" | "bearish";
  estimated_days: number | null;
}

export interface TechnicalAnalysis {
  support_levels: SupportResistanceLevel[];
  resistance_levels: SupportResistanceLevel[];
  trendlines: TrendLine[];
  patterns: ChartPattern[];
  projections: PriceProjection[];
  trend_summary: string;
}

export interface ChartData {
  symbol: string;
  bars: ChartBar[];
  signals: Signal[];
  technical_analysis: TechnicalAnalysis | null;
}

// --- Dark Pool ---

export interface DarkPoolEntry {
  symbol: string;
  date: string;
  short_volume: number;
  short_exempt_volume: number;
  total_volume: number;
  short_pct: number;
}

export interface DarkPoolResult {
  symbol: string;
  entries: DarkPoolEntry[];
  avg_short_pct: number;
  recent_short_pct: number;
  trend: "accumulating" | "distributing" | "neutral";
  trend_strength: number;
  price_change_pct: number;
  alert_reasons: string[];
}

// --- Earnings Whisper ---

export interface EarningsEvent {
  symbol: string;
  date: string;
  eps_estimate: number | null;
  eps_actual: number | null;
  revenue_estimate: number | null;
  revenue_actual: number | null;
  time: string;
}

export interface InsiderTrade {
  symbol: string;
  insider_name: string;
  title: string;
  transaction_type: "purchase" | "sale";
  shares: number;
  price: number;
  total_value: number;
  filing_date: string;
}

export interface EarningsConviction {
  symbol: string;
  earnings_date: string;
  conviction_score: number;
  eps_surprise_history: number[];
  insider_sentiment: "buying" | "selling" | "neutral";
  analyst_revisions: "up" | "down" | "stable";
  components: Record<string, number>;
  alert_reasons: string[];
}

// --- Options Flow ---

export interface OptionsContract {
  symbol: string;
  expiration: string;
  strike: number;
  contract_type: "call" | "put";
  volume: number;
  open_interest: number;
  vol_oi_ratio: number;
  implied_volatility: number | null;
  last_price: number | null;
}

export interface OptionsFlowResult {
  symbol: string;
  unusual_contracts: OptionsContract[];
  put_call_ratio: number;
  total_call_volume: number;
  total_put_volume: number;
  flow_sentiment: "bullish" | "bearish" | "neutral";
  alert_reasons: string[];
}
