"""Market breadth dashboard, economic calendar, and misc data features.

Features: 19 (relative volume), 60 (social sentiment proxy),
61 (market breadth), 62 (economic calendar), 70 (crypto fear/greed).
"""

import logging

import numpy as np
import requests

from src.data import client as alpaca_client
from src.data.cache import Cache
from src.scanner.screener import get_default_universe

logger = logging.getLogger("mse.breadth")
_cache = Cache()


# --- 61. Market Breadth Dashboard ---

def compute_market_breadth() -> dict:
    """Compute market breadth indicators across the universe."""
    cache_key = "market_breadth"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    symbols = [s for s in get_default_universe() if "/" not in s and s not in ("SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV")]
    above_20 = 0
    above_50 = 0
    above_200 = 0
    advancing = 0
    declining = 0
    new_highs = 0
    new_lows = 0
    total = 0

    for sym in symbols:
        try:
            df = alpaca_client.get_bars(sym, days=250)
            if df is None or len(df) < 50:
                continue

            close = df["close"]
            current = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) >= 2 else current
            sma20 = float(close.rolling(20).mean().iloc[-1])
            sma50 = float(close.rolling(50).mean().iloc[-1])

            total += 1
            if current > sma20:
                above_20 += 1
            if current > sma50:
                above_50 += 1
            if len(close) >= 200:
                sma200 = float(close.rolling(200).mean().iloc[-1])
                if current > sma200:
                    above_200 += 1

            if current > prev:
                advancing += 1
            elif current < prev:
                declining += 1

            high_252 = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
            low_252 = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())
            if current >= high_252 * 0.98:
                new_highs += 1
            if current <= low_252 * 1.02:
                new_lows += 1

        except Exception:
            continue

    if total == 0:
        return {"error": "No data"}

    ad_ratio = advancing / declining if declining > 0 else advancing

    result = {
        "total_stocks": total,
        "advancing": advancing,
        "declining": declining,
        "unchanged": total - advancing - declining,
        "ad_ratio": round(ad_ratio, 2),
        "above_20sma_pct": round(above_20 / total * 100, 1),
        "above_50sma_pct": round(above_50 / total * 100, 1),
        "above_200sma_pct": round(above_200 / total * 100, 1) if above_200 > 0 else 0,
        "new_52w_highs": new_highs,
        "new_52w_lows": new_lows,
        "breadth_signal": "bullish" if above_50 / total > 0.6 else "bearish" if above_50 / total < 0.4 else "neutral",
    }

    _cache.set(cache_key, result)
    return result


# --- 19. Relative Volume by Time ---

def get_relative_volume_profile(symbol: str) -> dict:
    """Analyze volume distribution pattern for a symbol."""
    try:
        from alpaca.data.timeframe import TimeFrame
        df = alpaca_client.get_bars(symbol, timeframe=TimeFrame.Hour, days=10)
        if df is None or len(df) < 20:
            return {"symbol": symbol, "error": "Insufficient data"}

        df["hour"] = df.index.hour if hasattr(df.index, 'hour') else 12
        hourly_avg = df.groupby("hour")["volume"].mean()

        profile = [
            {"hour": int(h), "avg_volume": int(v), "label": f"{int(h)}:00"}
            for h, v in hourly_avg.items()
        ]

        peak_hour = int(hourly_avg.idxmax()) if len(hourly_avg) > 0 else 0
        return {
            "symbol": symbol,
            "profile": sorted(profile, key=lambda x: x["hour"]),
            "peak_hour": peak_hour,
            "peak_label": f"{peak_hour}:00",
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


# --- 62. Economic Calendar ---

def get_economic_calendar() -> list[dict]:
    """Get economic events from FMP."""
    cache_key = "econ_calendar"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    from src.data.fmp_client import _get as fmp_get
    data = fmp_get("/v3/economic_calendar", {"limit": 30}, cache_key="fmp_econ")
    if not data:
        return []

    results = [
        {
            "event": item.get("event", ""),
            "date": item.get("date", ""),
            "country": item.get("country", ""),
            "actual": item.get("actual"),
            "previous": item.get("previous"),
            "estimate": item.get("estimate"),
            "impact": item.get("impact", ""),
        }
        for item in data[:30]
        if item.get("event")
    ]

    if results:
        _cache.set(cache_key, results)
    return results


# --- 70. Crypto Fear & Greed Index ---

def get_crypto_fear_greed() -> dict:
    """Get the crypto fear and greed index (free API)."""
    cache_key = "crypto_fg"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=7", timeout=10)
        if resp.status_code != 200:
            return {"error": "API unavailable"}

        data = resp.json().get("data", [])
        if not data:
            return {"error": "No data"}

        current = data[0]
        history = [
            {
                "value": int(d["value"]),
                "classification": d["value_classification"],
                "date": d.get("timestamp", ""),
            }
            for d in data
        ]

        result = {
            "value": int(current["value"]),
            "classification": current["value_classification"],
            "history": history,
        }
        _cache.set(cache_key, result)
        return result
    except Exception as e:
        return {"error": str(e)}
