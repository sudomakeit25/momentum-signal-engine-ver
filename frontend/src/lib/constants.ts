import type { SetupType } from "@/types/api";

export const SETUP_TYPE_COLORS: Record<SetupType, string> = {
  ema_crossover: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  breakout: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  rsi_pullback: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  vwap_reclaim: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  flag: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  flat_base: "bg-rose-500/20 text-rose-400 border-rose-500/30",
  tight_consolidation: "bg-slate-500/20 text-slate-400 border-slate-500/30",
  gap_up: "bg-orange-500/20 text-orange-400 border-orange-500/30",
};

export const SETUP_TYPE_LABELS: Record<SetupType, string> = {
  ema_crossover: "EMA Cross",
  breakout: "Breakout",
  rsi_pullback: "RSI Pullback",
  vwap_reclaim: "VWAP Reclaim",
  flag: "Flag",
  flat_base: "Flat Base",
  tight_consolidation: "Tight Range",
  gap_up: "Gap Up",
};

export const SCAN_REFRESH_MS = 30_000;
export const CHART_REFRESH_MS = 60_000;

export const DEFAULT_UNIVERSE = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
  "NFLX", "CRM", "ADBE", "ORCL", "AVGO", "QCOM", "INTC", "MU",
  "SHOP", "SQ", "PYPL", "COIN", "MARA", "RIOT", "SOFI", "PLTR",
  "SNOW", "DDOG", "NET", "CRWD", "ZS", "PANW", "ABNB", "UBER",
  "DASH", "RBLX", "U", "TTD", "ENPH", "SEDG", "FSLR", "CEG",
  "LLY", "UNH", "JNJ", "PFE", "ABBV", "MRK", "BMY", "AMGN",
  "TMO", "ABT", "DHR", "ISRG", "MDT", "GILD", "VRTX", "REGN",
  "XOM", "CVX", "COP", "SLB", "OXY", "DVN", "MPC", "PSX",
  "EOG", "HES", "VLO", "HAL",
  "JPM", "BAC", "GS", "MS", "WFC", "C", "SCHW", "BLK",
  "AXP", "COF", "ICE", "CME", "SPGI", "MMC",
  "CAT", "DE", "HON", "GE", "RTX", "LMT", "BA", "NOC",
  "UNP", "UPS", "FDX", "WM", "EMR", "ITW",
  "WMT", "COST", "HD", "LOW", "TGT", "NKE", "SBUX", "MCD",
  "PG", "KO", "PEP", "CL", "EL", "MNST",
  "DIS", "CMCSA", "T", "VZ", "CHTR", "TMUS",
  "LRCX", "KLAC", "AMAT", "MRVL", "ON", "SWKS", "TXN",
  "NOW", "INTU", "WDAY", "TEAM", "ZM", "OKTA", "MDB", "HUBS",
  "AMT", "PLD", "CCI", "EQIX", "NEE", "DUK", "SO", "AEP",
  "LIN", "APD", "SHW", "ECL", "NEM", "FCX",
  "SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV",
  "BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "AVAX/USD", "LINK/USD",
];
