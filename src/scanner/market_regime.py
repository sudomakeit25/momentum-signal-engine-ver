"""Market Regime Detector - classify current market conditions.

Uses SPY price action, volatility, trend strength, and breadth
to classify the market as trending, choppy, or volatile.
Adjusts signal confidence recommendations accordingly.
"""

import logging

import numpy as np
import pandas as pd

from src.data import client as alpaca_client
from src.data.cache import Cache

logger = logging.getLogger("mse.regime")
_cache = Cache()


def _default_regime() -> dict:
    """Return a default neutral regime when data is unavailable."""
    return {
        "regime": "unknown",
        "confidence_adjustment": 1.0,
        "description": "Unable to determine market regime (insufficient data).",
        "components": {
            "trend_strength": 0,
            "trend_direction": "unknown",
            "volatility": 0,
            "volatility_level": "unknown",
            "breadth": 0,
            "momentum": 0,
        },
        "recommendation": {"bias": "neutral", "position_size": "reduced", "stop_width": "normal"},
        "spy_price": 0,
        "spy_change_20d": 0,
    }


def detect_regime(days: int = 100) -> dict:
    """Detect current market regime from SPY data.

    Returns regime classification with component scores.
    """
    cache_key = f"market_regime_{days}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        df = alpaca_client.get_bars("SPY", days=days)
    except Exception:
        return _default_regime()

    if df is None or len(df) < 50:
        return _default_regime()

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # 1. Trend Strength (ADX proxy using directional movement)
    trend_score, trend_direction = _compute_trend(close)

    # 2. Volatility (ATR-based)
    vol_score, vol_level = _compute_volatility(high, low, close)

    # 3. Breadth (price vs moving averages)
    breadth_score = _compute_breadth(close)

    # 4. Momentum (rate of change)
    momentum_score = _compute_momentum(close)

    # Classify regime
    regime, confidence_adj = _classify(trend_score, vol_score, breadth_score, momentum_score)

    result = {
        "regime": regime,
        "confidence_adjustment": confidence_adj,
        "description": _describe(regime),
        "components": {
            "trend_strength": round(trend_score, 2),
            "trend_direction": trend_direction,
            "volatility": round(vol_score, 2),
            "volatility_level": vol_level,
            "breadth": round(breadth_score, 2),
            "momentum": round(momentum_score, 2),
        },
        "recommendation": _recommend(regime),
        "spy_price": round(float(close.iloc[-1]), 2),
        "spy_change_20d": round(float((close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100), 2) if len(close) >= 20 else 0,
    }

    _cache.set(cache_key, result)
    return result


def _compute_trend(close: pd.Series) -> tuple[float, str]:
    """Compute trend strength (0=no trend, 1=strong trend)."""
    ema9 = close.ewm(span=9).mean()
    ema21 = close.ewm(span=21).mean()
    ema50 = close.ewm(span=50).mean()

    # EMA alignment score
    aligned_bullish = (ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1])
    aligned_bearish = (ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1])

    # Slope of 20-day regression
    recent = close.iloc[-20:].values
    x = np.arange(len(recent))
    slope = np.polyfit(x, recent, 1)[0]
    norm_slope = abs(slope) / close.iloc[-1] * 100  # as % per day

    if aligned_bullish:
        direction = "bullish"
        strength = min(0.5 + norm_slope * 5, 1.0)
    elif aligned_bearish:
        direction = "bearish"
        strength = min(0.5 + norm_slope * 5, 1.0)
    else:
        direction = "mixed"
        strength = min(norm_slope * 3, 0.4)

    return strength, direction


def _compute_volatility(high: pd.Series, low: pd.Series, close: pd.Series) -> tuple[float, str]:
    """Compute volatility score (0=calm, 1=extremely volatile)."""
    # Average True Range (14-period)
    tr = pd.DataFrame({
        "hl": high - low,
        "hc": abs(high - close.shift(1)),
        "lc": abs(low - close.shift(1)),
    }).max(axis=1)

    atr14 = tr.rolling(14).mean().iloc[-1]
    atr_pct = atr14 / close.iloc[-1] * 100

    # Historical ATR comparison
    atr_series = tr.rolling(14).mean().dropna()
    if len(atr_series) > 20:
        atr_mean = atr_series.mean()
        atr_std = atr_series.std()
        z = (atr14 - atr_mean) / atr_std if atr_std > 0 else 0
    else:
        z = 0

    vol_score = min(max((atr_pct - 0.5) / 2.0, 0), 1.0)

    if atr_pct > 2.0 or z > 1.5:
        level = "high"
    elif atr_pct > 1.0:
        level = "moderate"
    else:
        level = "low"

    return vol_score, level


def _compute_breadth(close: pd.Series) -> float:
    """Compute market breadth score (-1 to 1).

    Positive = price above MAs (healthy), negative = below MAs (weak).
    """
    current = close.iloc[-1]
    sma20 = close.rolling(20).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]

    score = 0.0
    if current > sma20:
        score += 0.5
    else:
        score -= 0.5

    if current > sma50:
        score += 0.5
    else:
        score -= 0.5

    return score


def _compute_momentum(close: pd.Series) -> float:
    """Compute momentum score (-1 to 1)."""
    if len(close) < 20:
        return 0.0

    roc_5 = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]
    roc_20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]

    score = (roc_5 * 0.6 + roc_20 * 0.4) * 10  # scale up
    return max(min(score, 1.0), -1.0)


def _classify(trend: float, vol: float, breadth: float, momentum: float) -> tuple[str, float]:
    """Classify market regime. Returns (regime, confidence_adjustment).

    Confidence adjustment: multiplier for signal confidence.
    > 1.0 = increase confidence, < 1.0 = decrease confidence.
    """
    if vol > 0.7:
        if trend > 0.6:
            return "volatile_trending", 0.8
        return "volatile_choppy", 0.6

    if trend > 0.6 and breadth > 0:
        if momentum > 0.3:
            return "strong_uptrend", 1.2
        return "uptrend", 1.1

    if trend > 0.6 and breadth < 0:
        if momentum < -0.3:
            return "strong_downtrend", 1.1
        return "downtrend", 0.9

    if trend < 0.3:
        return "range_bound", 0.7

    return "transitional", 0.85


def _describe(regime: str) -> str:
    descriptions = {
        "strong_uptrend": "Strong bullish trend with positive breadth and momentum. Favor long setups.",
        "uptrend": "Bullish trend in place. Standard long bias applies.",
        "strong_downtrend": "Strong bearish trend. Consider defensive positioning or short setups.",
        "downtrend": "Bearish pressure. Reduce position sizes and be selective.",
        "volatile_trending": "High volatility with directional bias. Use wider stops.",
        "volatile_choppy": "High volatility with no clear direction. Reduce exposure significantly.",
        "range_bound": "Low trend strength. Mean reversion strategies may outperform.",
        "transitional": "Market transitioning between regimes. Wait for clarity.",
    }
    return descriptions.get(regime, "Unknown regime")


def _recommend(regime: str) -> dict:
    recs = {
        "strong_uptrend": {"bias": "long", "position_size": "full", "stop_width": "normal"},
        "uptrend": {"bias": "long", "position_size": "full", "stop_width": "normal"},
        "strong_downtrend": {"bias": "short", "position_size": "reduced", "stop_width": "tight"},
        "downtrend": {"bias": "cautious", "position_size": "reduced", "stop_width": "tight"},
        "volatile_trending": {"bias": "trend", "position_size": "reduced", "stop_width": "wide"},
        "volatile_choppy": {"bias": "neutral", "position_size": "minimal", "stop_width": "wide"},
        "range_bound": {"bias": "neutral", "position_size": "reduced", "stop_width": "tight"},
        "transitional": {"bias": "neutral", "position_size": "reduced", "stop_width": "normal"},
    }
    return recs.get(regime, {"bias": "neutral", "position_size": "normal", "stop_width": "normal"})
