"""Multi-timeframe analysis - weekly + daily + intraday signals side by side."""

import logging

import pandas as pd
from alpaca.data.timeframe import TimeFrame

from src.data import client as alpaca_client
from src.signals.generator import generate_signals
from src.signals.indicators import add_all_indicators

logger = logging.getLogger("mse.multi_tf")

TIMEFRAMES = {
    "weekly": {"timeframe": TimeFrame.Week, "days": 500, "label": "Weekly"},
    "daily": {"timeframe": TimeFrame.Day, "days": 200, "label": "Daily"},
    "hourly": {"timeframe": TimeFrame.Hour, "days": 30, "label": "Hourly"},
}


def analyze_multi_timeframe(symbol: str) -> dict:
    """Analyze a symbol across weekly, daily, and hourly timeframes.

    Returns signals, trend direction, and key levels for each timeframe.
    """
    results = {}

    for tf_key, tf_config in TIMEFRAMES.items():
        try:
            df = alpaca_client.get_bars(
                symbol,
                timeframe=tf_config["timeframe"],
                days=tf_config["days"],
            )

            if df is None or len(df) < 20:
                results[tf_key] = {
                    "label": tf_config["label"],
                    "trend": "unknown",
                    "signals": [],
                    "summary": "Insufficient data",
                    "bars": 0,
                }
                continue

            df = add_all_indicators(df)
            close = df["close"]

            # Trend detection
            ema9 = close.ewm(span=9).mean().iloc[-1]
            ema21 = close.ewm(span=21).mean().iloc[-1]
            ema50 = close.ewm(span=50).mean().iloc[-1] if len(close) >= 50 else ema21
            current = close.iloc[-1]

            if ema9 > ema21 > ema50:
                trend = "bullish"
            elif ema9 < ema21 < ema50:
                trend = "bearish"
            elif ema9 > ema21:
                trend = "turning_bullish"
            elif ema9 < ema21:
                trend = "turning_bearish"
            else:
                trend = "neutral"

            # RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1] if len(rs.dropna()) > 0 else 50

            # Generate signals
            try:
                signals = generate_signals(df, symbol)
                signal_list = [
                    {
                        "action": s.action.value,
                        "setup_type": s.setup_type.value,
                        "entry": s.entry,
                        "target": s.target,
                        "stop_loss": s.stop_loss,
                        "confidence": s.confidence,
                        "reason": s.reason[:100],
                    }
                    for s in signals
                ]
            except Exception:
                signal_list = []

            # Key levels
            high_20 = float(close.iloc[-20:].max()) if len(close) >= 20 else float(close.max())
            low_20 = float(close.iloc[-20:].min()) if len(close) >= 20 else float(close.min())

            results[tf_key] = {
                "label": tf_config["label"],
                "trend": trend,
                "price": float(current),
                "ema9": round(float(ema9), 2),
                "ema21": round(float(ema21), 2),
                "rsi": round(float(rsi), 1),
                "high_20": round(high_20, 2),
                "low_20": round(low_20, 2),
                "signals": signal_list,
                "signal_count": len(signal_list),
                "bars": len(df),
                "summary": _summarize(trend, float(rsi), signal_list),
            }

        except Exception as e:
            logger.debug("Multi-TF analysis failed for %s/%s: %s", symbol, tf_key, e)
            results[tf_key] = {
                "label": tf_config["label"],
                "trend": "error",
                "signals": [],
                "summary": f"Analysis failed: {str(e)[:50]}",
                "bars": 0,
            }

    # Overall alignment
    trends = [r.get("trend", "unknown") for r in results.values()]
    bullish_count = sum(1 for t in trends if t in ("bullish", "turning_bullish"))
    bearish_count = sum(1 for t in trends if t in ("bearish", "turning_bearish"))

    if bullish_count >= 2:
        alignment = "bullish"
        alignment_strength = bullish_count / len(trends)
    elif bearish_count >= 2:
        alignment = "bearish"
        alignment_strength = bearish_count / len(trends)
    else:
        alignment = "mixed"
        alignment_strength = 0

    return {
        "symbol": symbol,
        "timeframes": results,
        "alignment": alignment,
        "alignment_strength": round(alignment_strength, 2),
        "recommendation": _recommend(alignment, results),
    }


def _summarize(trend: str, rsi: float, signals: list) -> str:
    trend_text = {
        "bullish": "Bullish (EMAs aligned up)",
        "bearish": "Bearish (EMAs aligned down)",
        "turning_bullish": "Turning bullish (EMA 9 > 21)",
        "turning_bearish": "Turning bearish (EMA 9 < 21)",
        "neutral": "Neutral (no clear direction)",
    }.get(trend, "Unknown")

    rsi_text = ""
    if rsi > 70:
        rsi_text = ", RSI overbought"
    elif rsi < 30:
        rsi_text = ", RSI oversold"

    sig_text = f", {len(signals)} signals" if signals else ""

    return f"{trend_text}{rsi_text}{sig_text}"


def _recommend(alignment: str, results: dict) -> str:
    if alignment == "bullish":
        return "All timeframes aligned bullish. High-confidence long setups favored."
    elif alignment == "bearish":
        return "All timeframes aligned bearish. Avoid longs or consider short setups."
    else:
        return "Mixed signals across timeframes. Be selective and use tight stops."
