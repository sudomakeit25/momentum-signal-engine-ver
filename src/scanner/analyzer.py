"""Per-symbol analyzer - consolidated trend / momentum / risk report.

Pulls daily bars for a symbol (plus SPY for RS) and produces a single,
UI-friendly dict with component scores and a verdict. Intended for a
detail-view page rather than scanning.
"""

import logging

import pandas as pd

from src.data import client
from src.signals.indicators import atr, ema, macd, relative_strength_vs_spy, rsi, volume_sma

logger = logging.getLogger("mse.analyzer")


def _grade(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def _verdict(total: float, trend: str) -> str:
    if total >= 75 and trend == "bullish":
        return "strong_buy"
    if total >= 60 and trend in ("bullish", "turning_bullish"):
        return "buy"
    if total >= 40:
        return "hold"
    return "avoid"


def _trend_label(ema9: float, ema21: float, ema50: float) -> str:
    if ema9 > ema21 > ema50:
        return "bullish"
    if ema9 < ema21 < ema50:
        return "bearish"
    if ema9 > ema21:
        return "turning_bullish"
    if ema9 < ema21:
        return "turning_bearish"
    return "neutral"


def analyze_symbol(symbol: str, days: int = 260) -> dict:
    """Produce a consolidated analysis report for a symbol."""
    symbol = symbol.upper()
    try:
        df = client.get_bars(symbol, days=days)
    except Exception as e:
        return {"symbol": symbol, "error": f"fetch failed: {e}"}

    if df is None or len(df) < 60:
        return {"symbol": symbol, "error": "insufficient history"}

    try:
        spy_df = client.get_bars("SPY", days=days)
    except Exception:
        spy_df = pd.DataFrame()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else price
    change_pct = (price - prev_close) / prev_close * 100 if prev_close else 0.0

    ema9 = float(ema(close, 9).iloc[-1])
    ema21 = float(ema(close, 21).iloc[-1])
    ema50 = float(ema(close, 50).iloc[-1]) if len(close) >= 50 else ema21
    ema200 = float(ema(close, 200).iloc[-1]) if len(close) >= 200 else ema50
    rsi_val = float(rsi(close).iloc[-1])
    macd_line, macd_sig, macd_hist = macd(close)
    macd_hist_val = float(macd_hist.iloc[-1]) if len(macd_hist.dropna()) else 0.0
    atr_val = float(atr(df).iloc[-1])
    atr_pct = atr_val / price * 100 if price else 0.0

    high_52w = float(close.tail(252).max()) if len(close) >= 100 else float(close.max())
    low_52w = float(close.tail(252).min()) if len(close) >= 100 else float(close.min())
    pct_off_high = (price - high_52w) / high_52w * 100 if high_52w else 0.0
    pct_above_low = (price - low_52w) / low_52w * 100 if low_52w else 0.0

    rs_val = 0.0
    if len(close) >= 63 and len(spy_df) >= 63:
        rs_series = relative_strength_vs_spy(close, spy_df["close"], 63)
        rs_val = float(rs_series.iloc[-1]) if pd.notna(rs_series.iloc[-1]) else 0.0

    avg_vol = float(volume_sma(volume, 20).iloc[-1])
    rel_vol = float(volume.iloc[-1]) / avg_vol if avg_vol > 0 else 0.0
    dollar_vol = price * avg_vol

    trend = _trend_label(ema9, ema21, ema50)

    # Component scores (0-100)
    trend_score = 0.0
    if ema9 > ema21:
        trend_score += 25
    if ema21 > ema50:
        trend_score += 25
    if ema50 > ema200:
        trend_score += 25
    if price > ema21:
        trend_score += 25

    momentum_score = 0.0
    if 50 <= rsi_val <= 70:
        momentum_score += 40
    elif 40 <= rsi_val < 50 or 70 < rsi_val <= 75:
        momentum_score += 25
    elif rsi_val > 75:
        momentum_score += 10
    if macd_hist_val > 0:
        momentum_score += 30
    if change_pct > 0:
        momentum_score += 30
    momentum_score = min(momentum_score, 100)

    quality_score = 0.0
    if rs_val >= 1.10:
        quality_score += 45
    elif rs_val >= 1.0:
        quality_score += 30
    elif rs_val >= 0.95:
        quality_score += 15
    if pct_off_high > -5:
        quality_score += 35
    elif pct_off_high > -15:
        quality_score += 20
    elif pct_off_high > -30:
        quality_score += 5
    if pct_above_low > 30:
        quality_score += 20
    quality_score = min(quality_score, 100)

    # Risk score: higher = safer. Penalize high ATR% and deep drawdowns.
    risk_score = 100.0
    if atr_pct > 8:
        risk_score -= 40
    elif atr_pct > 5:
        risk_score -= 25
    elif atr_pct > 3:
        risk_score -= 10
    if pct_off_high < -30:
        risk_score -= 30
    elif pct_off_high < -15:
        risk_score -= 15
    if dollar_vol < 5_000_000:
        risk_score -= 20
    elif dollar_vol < 20_000_000:
        risk_score -= 5
    risk_score = max(risk_score, 0.0)

    composite = (
        trend_score * 0.30
        + momentum_score * 0.30
        + quality_score * 0.25
        + risk_score * 0.15
    )

    strengths: list[str] = []
    weaknesses: list[str] = []
    if ema9 > ema21 > ema50 > ema200:
        strengths.append("EMAs fully stacked bullishly")
    if rs_val >= 1.10:
        strengths.append(f"Outperforming SPY (RS {rs_val:.2f})")
    if pct_off_high > -5:
        strengths.append("Trading near 52-week high")
    if macd_hist_val > 0 and rsi_val >= 50:
        strengths.append("MACD and RSI both constructive")
    if rel_vol >= 1.5:
        strengths.append(f"Volume surge ({rel_vol:.2f}x avg)")

    if rsi_val > 75:
        weaknesses.append("RSI overbought - pullback risk")
    if rsi_val < 30:
        weaknesses.append("RSI oversold - no confirmed bottom")
    if atr_pct > 6:
        weaknesses.append(f"High volatility (ATR {atr_pct:.1f}%)")
    if pct_off_high < -20:
        weaknesses.append(f"{abs(pct_off_high):.0f}% off 52w high")
    if rs_val < 0.95:
        weaknesses.append("Lagging SPY")
    if ema50 < ema200:
        weaknesses.append("50 EMA below 200 EMA (long-term weakness)")

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "change_pct": round(change_pct, 2),
        "trend": trend,
        "verdict": _verdict(composite, trend),
        "grade": _grade(composite),
        "composite_score": round(composite, 1),
        "scores": {
            "trend": round(trend_score, 1),
            "momentum": round(momentum_score, 1),
            "quality": round(quality_score, 1),
            "risk": round(risk_score, 1),
        },
        "indicators": {
            "ema9": round(ema9, 2),
            "ema21": round(ema21, 2),
            "ema50": round(ema50, 2),
            "ema200": round(ema200, 2),
            "rsi": round(rsi_val, 1),
            "macd_hist": round(macd_hist_val, 3),
            "atr": round(atr_val, 2),
            "atr_pct": round(atr_pct, 2),
            "relative_strength": round(rs_val, 3),
            "rel_volume": round(rel_vol, 2),
            "avg_volume": int(avg_vol),
            "dollar_volume": int(dollar_vol),
        },
        "range_52w": {
            "high": round(high_52w, 2),
            "low": round(low_52w, 2),
            "pct_off_high": round(pct_off_high, 1),
            "pct_above_low": round(pct_above_low, 1),
        },
        "strengths": strengths,
        "weaknesses": weaknesses,
    }
