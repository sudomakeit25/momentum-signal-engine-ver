"""Indicator time series for the Overbought-Oversold tab.

Returns daily RSI, MACD line/signal/histogram, and Bollinger band
position so the frontend can plot them alongside price.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.data import client
from src.signals.indicators import ema, macd, rsi, sma

logger = logging.getLogger("mse.instrument_indicators")


def _dpo(close: pd.Series, period: int = 20) -> pd.Series:
    """Detrended Price Oscillator: close[n/2+1 ago] - SMA(close, n)."""
    shift = period // 2 + 1
    return close.shift(shift) - sma(close, period)


def _stochastic(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> tuple[pd.Series, pd.Series]:
    """Stochastic %K and %D."""
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    k = 100 * (close - lowest) / (highest - lowest)
    d = k.rolling(3).mean()
    return k, d


def _williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Williams %R: -100 * (highest - close) / (highest - lowest)."""
    highest = high.rolling(period).max()
    lowest = low.rolling(period).min()
    return -100 * (highest - close) / (highest - lowest)


def _roc(close: pd.Series, period: int) -> pd.Series:
    """Rate of Change: (close / close[n ago] - 1) * 100."""
    return (close / close.shift(period) - 1) * 100


def _ad_line(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Chaikin Accumulation/Distribution Line.

    MFM = ((close - low) - (high - close)) / (high - low)
    MFV = MFM * volume
    A/D = cumulative sum of MFV
    """
    rng = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / rng
    mfv = (mfm * volume).fillna(0)
    return mfv.cumsum()


def _wyckoff_phase(
    close: pd.Series,
    volume: pd.Series,
    ad: pd.Series,
) -> tuple[str, str]:
    """Simplified Wyckoff-phase classifier.

    Compares recent 30-bar behavior:
      - Price: is it trending up / down / flat
      - Volume: is it expanding or contracting
      - A/D line: is it confirming price (aligned slopes) or diverging

    Returns (phase, description) where phase is one of:
      markup     — uptrend + volume confirmation
      distribution — flat/down near highs + volume expansion
      markdown   — downtrend + volume confirmation
      accumulation — flat/up near lows + volume contraction
      neutral    — inconclusive
    """
    if len(close) < 40:
        return "neutral", "insufficient history"
    window = 30
    c = close.tail(window)
    v = volume.tail(window)
    a = ad.tail(window)

    price_slope_pct = (c.iloc[-1] / c.iloc[0] - 1) * 100 if c.iloc[0] > 0 else 0.0
    vol_now = v.tail(10).mean()
    vol_prev = v.head(10).mean()
    vol_expanding = vol_prev > 0 and (vol_now / vol_prev) > 1.2
    ad_slope = a.iloc[-1] - a.iloc[0]

    near_hi = close.iloc[-1] >= close.tail(60).max() * 0.95
    near_lo = close.iloc[-1] <= close.tail(60).min() * 1.05

    if price_slope_pct > 5 and ad_slope > 0:
        return "markup", f"Uptrend confirmed by rising A/D (+{price_slope_pct:.1f}% in 30 bars)"
    if price_slope_pct < -5 and ad_slope < 0:
        return "markdown", f"Downtrend confirmed by falling A/D ({price_slope_pct:.1f}% in 30 bars)"
    if near_hi and abs(price_slope_pct) < 5 and vol_expanding and ad_slope <= 0:
        return "distribution", "Flat near highs with expanding volume and weakening A/D"
    if near_lo and abs(price_slope_pct) < 5 and not vol_expanding and ad_slope >= 0:
        return "accumulation", "Flat near lows with contracting volume and rising A/D"
    return "neutral", f"No clear phase (price {price_slope_pct:+.1f}%, A/D slope {ad_slope:+.0f})"


def get_indicator_series(symbol: str, days: int = 260) -> dict:
    symbol = symbol.upper()
    try:
        df = client.get_bars(symbol, days=days)
    except Exception as e:
        return {"symbol": symbol, "error": f"fetch failed: {e}"}

    if df is None or df.empty or len(df) < 60:
        return {"symbol": symbol, "error": "insufficient history"}

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    rsi_s = rsi(close).dropna()
    macd_line, macd_sig, macd_hist = macd(close)
    sma20 = sma(close, 20)
    std20 = close.rolling(20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20
    bb_pct = (close - bb_lower) / (bb_upper - bb_lower)
    dpo20 = _dpo(close, 20)
    dpo50 = _dpo(close, 50)
    stoch_k, stoch_d = _stochastic(high, low, close, 14)
    wr = _williams_r(high, low, close, 14)
    roc_10 = _roc(close, 10)
    roc_21 = _roc(close, 21)
    roc_63 = _roc(close, 63)
    volume = df["volume"].astype(float) if "volume" in df else pd.Series([], dtype=float)
    ad = _ad_line(high, low, close, volume) if len(volume) == len(close) else pd.Series([], dtype=float)
    wyckoff_phase, wyckoff_desc = _wyckoff_phase(close, volume, ad) if len(ad) else ("neutral", "no volume data")

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
        "dpo_20": _safe_round(dpo20.iloc[-1] if len(dpo20) else None, 2),
        "dpo_50": _safe_round(dpo50.iloc[-1] if len(dpo50) else None, 2),
        "stoch_k": _safe_round(stoch_k.iloc[-1] if len(stoch_k) else None, 2),
        "stoch_d": _safe_round(stoch_d.iloc[-1] if len(stoch_d) else None, 2),
        "williams_r": _safe_round(wr.iloc[-1] if len(wr) else None, 2),
        "roc_10": _safe_round(roc_10.iloc[-1] if len(roc_10) else None, 2),
        "roc_21": _safe_round(roc_21.iloc[-1] if len(roc_21) else None, 2),
        "roc_63": _safe_round(roc_63.iloc[-1] if len(roc_63) else None, 2),
    }

    # Market Mood Meter: composite 0-100 where 50 is neutral.
    # Inputs normalized to a common scale:
    #   RSI -> already 0-100
    #   Stochastic %K -> already 0-100
    #   Williams %R -> mapped from [-100, 0] to [0, 100]
    #   BB position -> clipped 0-100
    #   Momentum (10d ROC) -> mapped with a sigmoid-ish: clip [-10, +10] -> [0, 100]
    #   MACD hist relative to its own 3-month std -> clip [-2, +2] -> [0, 100]
    pieces: list[float] = []
    if snapshot["rsi"] is not None:
        pieces.append(snapshot["rsi"])
    if snapshot["stoch_k"] is not None:
        pieces.append(snapshot["stoch_k"])
    if snapshot["williams_r"] is not None:
        pieces.append(100 + snapshot["williams_r"])  # maps -100..0 -> 0..100
    if snapshot["bb_pct"] is not None:
        pieces.append(max(0.0, min(100.0, snapshot["bb_pct"] * 100)))
    if snapshot["roc_10"] is not None:
        clipped = max(-10.0, min(10.0, snapshot["roc_10"]))
        pieces.append(50 + clipped * 5)
    if _last(macd_hist) is not None:
        hist_std = float(macd_hist.tail(63).std()) or 1.0
        hist_norm = max(-2.0, min(2.0, snapshot["macd_hist"] / hist_std if hist_std else 0.0))
        pieces.append(50 + hist_norm * 25)

    mood_score: float | None = None
    mood_label = "neutral"
    if pieces:
        mood_score = round(float(np.mean(pieces)), 1)
        if mood_score >= 80:
            mood_label = "extreme_greed"
        elif mood_score >= 65:
            mood_label = "greed"
        elif mood_score >= 55:
            mood_label = "bullish"
        elif mood_score >= 45:
            mood_label = "neutral"
        elif mood_score >= 35:
            mood_label = "bearish"
        elif mood_score >= 20:
            mood_label = "fear"
        else:
            mood_label = "extreme_fear"

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
            "dpo_20": _safe_round(dpo20.get(idx), 2),
            "stoch_k": _safe_round(stoch_k.get(idx), 2),
            "stoch_d": _safe_round(stoch_d.get(idx), 2),
            "williams_r": _safe_round(wr.get(idx), 2),
            "roc_21": _safe_round(roc_21.get(idx), 2),
        })

    verdict = _rsi_verdict(snapshot["rsi"])

    # Normalize A/D for plotting (scale to 0-100 over the visible window)
    ad_series: list[float | None] = []
    if len(ad):
        tail_ad = ad.tail(tail_bars)
        if len(tail_ad):
            lo = float(tail_ad.min())
            hi = float(tail_ad.max())
            span = hi - lo if hi != lo else 1.0
            for idx in close.index[-tail_bars:]:
                v = ad.get(idx)
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    ad_series.append(None)
                else:
                    ad_series.append(round((float(v) - lo) / span * 100, 2))
    # Pad to same length as `series`
    while len(ad_series) < len(series):
        ad_series.append(None)
    for i, rec in enumerate(series):
        rec["ad_norm"] = ad_series[i] if i < len(ad_series) else None

    return {
        "symbol": symbol,
        "snapshot": snapshot,
        "series": series,
        "verdict": verdict,
        "mood": {
            "score": mood_score,
            "label": mood_label,
        },
        "wyckoff": {
            "phase": wyckoff_phase,
            "description": wyckoff_desc,
        },
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
