"""Indicator time series for the Overbought-Oversold tab.

Returns daily RSI, MACD line/signal/histogram, and Bollinger band
position so the frontend can plot them alongside price.
"""

from __future__ import annotations

import logging

from src.data import client
from src.signals.indicators import ema, macd, rsi, sma

logger = logging.getLogger("mse.instrument_indicators")


def get_indicator_series(symbol: str, days: int = 260) -> dict:
    symbol = symbol.upper()
    try:
        df = client.get_bars(symbol, days=days)
    except Exception as e:
        return {"symbol": symbol, "error": f"fetch failed: {e}"}

    if df is None or df.empty or len(df) < 60:
        return {"symbol": symbol, "error": "insufficient history"}

    close = df["close"].astype(float)

    rsi_s = rsi(close).dropna()
    macd_line, macd_sig, macd_hist = macd(close)
    sma20 = sma(close, 20)
    std20 = close.rolling(20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20
    bb_pct = (close - bb_lower) / (bb_upper - bb_lower)

    # Latest snapshots
    def _last(series):
        s = series.dropna()
        return float(s.iloc[-1]) if len(s) else None

    snapshot = {
        "price": round(float(close.iloc[-1]), 2),
        "rsi": round(_last(rsi_s), 2) if _last(rsi_s) is not None else None,
        "macd_line": round(_last(macd_line), 4) if _last(macd_line) is not None else None,
        "macd_signal": round(_last(macd_sig), 4) if _last(macd_sig) is not None else None,
        "macd_hist": round(_last(macd_hist), 4) if _last(macd_hist) is not None else None,
        "bb_upper": round(_last(bb_upper), 2) if _last(bb_upper) is not None else None,
        "bb_lower": round(_last(bb_lower), 2) if _last(bb_lower) is not None else None,
        "bb_pct": round(_last(bb_pct), 3) if _last(bb_pct) is not None else None,
    }

    # Time series (last ~120 bars, enough for chart but not huge payload)
    tail_bars = 120
    dates = close.index[-tail_bars:].strftime("%Y-%m-%d").tolist()
    series = []
    for i, d in enumerate(dates):
        idx = close.index[-tail_bars + i]
        series.append({
            "date": d,
            "close": round(float(close.loc[idx]), 2),
            "rsi": _safe_round(rsi_s.get(idx), 2),
            "macd": _safe_round(macd_line.get(idx), 4),
            "macd_signal": _safe_round(macd_sig.get(idx), 4),
            "macd_hist": _safe_round(macd_hist.get(idx), 4),
            "bb_upper": _safe_round(bb_upper.get(idx), 2),
            "bb_lower": _safe_round(bb_lower.get(idx), 2),
        })

    verdict = _rsi_verdict(snapshot["rsi"])

    return {
        "symbol": symbol,
        "snapshot": snapshot,
        "series": series,
        "verdict": verdict,
    }


def _safe_round(v, n: int):
    try:
        if v is None:
            return None
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
        return round(float(v), n)
    except Exception:
        return None


def _rsi_verdict(rsi_val: float | None) -> str:
    if rsi_val is None:
        return "unknown"
    if rsi_val >= 70:
        return "overbought"
    if rsi_val <= 30:
        return "oversold"
    if rsi_val >= 55:
        return "bullish"
    if rsi_val <= 45:
        return "bearish"
    return "neutral"
