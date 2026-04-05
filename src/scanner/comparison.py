"""Stock comparison, global markets, yield curve, usage analytics.

Features 55, 63-64, 69, 87.
"""

import logging
import json
from datetime import datetime, timezone

import numpy as np
import requests

from src.data import client as alpaca_client
from src.data.cache import Cache
from src.data.redis_store import _get_redis

logger = logging.getLogger("mse.comparison")
_cache = Cache()

_USAGE_KEY = "mse:usage_analytics"


# --- 55. Stock Comparison ---

def compare_stocks(symbols: list[str]) -> dict:
    """Compare multiple stocks side by side."""
    results = []
    for sym in symbols[:6]:  # max 6
        try:
            df = alpaca_client.get_bars(sym.upper(), days=200)
            if df is None or len(df) < 20:
                continue

            close = df["close"]
            current = float(close.iloc[-1])
            change_1d = (current - float(close.iloc[-2])) / float(close.iloc[-2]) * 100 if len(close) >= 2 else 0
            change_5d = (current - float(close.iloc[-5])) / float(close.iloc[-5]) * 100 if len(close) >= 5 else 0
            change_20d = (current - float(close.iloc[-20])) / float(close.iloc[-20]) * 100 if len(close) >= 20 else 0
            change_60d = (current - float(close.iloc[-60])) / float(close.iloc[-60]) * 100 if len(close) >= 60 else 0

            high_52w = float(close.max())
            low_52w = float(close.min())
            avg_vol = int(df["volume"].iloc[-20:].mean())

            ema9 = float(close.ewm(span=9).mean().iloc[-1])
            ema21 = float(close.ewm(span=21).mean().iloc[-1])
            ema_aligned = ema9 > ema21

            results.append({
                "symbol": sym.upper(),
                "price": round(current, 2),
                "change_1d": round(change_1d, 2),
                "change_5d": round(change_5d, 2),
                "change_20d": round(change_20d, 2),
                "change_60d": round(change_60d, 2),
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "pct_from_high": round((current - high_52w) / high_52w * 100, 2),
                "avg_volume": avg_vol,
                "ema_aligned": ema_aligned,
                "trend": "bullish" if ema_aligned else "bearish",
            })
        except Exception:
            continue

    return {"stocks": results, "count": len(results)}


# --- 63/64. Yield Curve / Treasury Rates ---

def get_yield_curve() -> dict:
    """Get treasury yield data (FMP)."""
    cache_key = "yield_curve"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    from src.data.fmp_client import _get as fmp_get
    data = fmp_get("/v4/treasury", {"limit": 1}, cache_key="fmp_treasury")
    if not data or not isinstance(data, list):
        return {"error": "Treasury data not available (FMP API key needed)"}

    latest = data[0] if data else {}
    maturities = {
        "1m": latest.get("month1", 0),
        "3m": latest.get("month3", 0),
        "6m": latest.get("month6", 0),
        "1y": latest.get("year1", 0),
        "2y": latest.get("year2", 0),
        "5y": latest.get("year5", 0),
        "10y": latest.get("year10", 0),
        "30y": latest.get("year30", 0),
    }

    # Check for inversion
    y2 = maturities.get("2y", 0)
    y10 = maturities.get("10y", 0)
    spread_2_10 = round(y10 - y2, 3) if y2 and y10 else 0
    inverted = spread_2_10 < 0

    result = {
        "date": latest.get("date", ""),
        "maturities": maturities,
        "spread_2_10": spread_2_10,
        "inverted": inverted,
        "signal": "recession_warning" if inverted else "normal",
    }
    _cache.set(cache_key, result)
    return result


# --- 69. Global Market Dashboard ---

def get_global_markets() -> dict:
    """Get global market ETF proxies."""
    cache_key = "global_markets"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    etfs = {
        "US (S&P 500)": "SPY",
        "US (Nasdaq)": "QQQ",
        "US (Russell 2000)": "IWM",
        "Europe": "VGK",
        "Japan": "EWJ",
        "China": "FXI",
        "Emerging Markets": "EEM",
        "Gold": "GLD",
        "Oil": "USO",
        "Bonds (TLT)": "TLT",
        "US Dollar": "UUP",
        "Real Estate": "VNQ",
    }

    results = []
    for label, sym in etfs.items():
        try:
            df = alpaca_client.get_bars(sym, days=30)
            if df is None or len(df) < 2:
                continue

            current = float(df["close"].iloc[-1])
            prev = float(df["close"].iloc[-2])
            change_1d = (current - prev) / prev * 100
            change_5d = (current - float(df["close"].iloc[-5])) / float(df["close"].iloc[-5]) * 100 if len(df) >= 5 else 0

            results.append({
                "label": label,
                "symbol": sym,
                "price": round(current, 2),
                "change_1d": round(change_1d, 2),
                "change_5d": round(change_5d, 2),
            })
        except Exception:
            continue

    result = {"markets": results}
    if results:
        _cache.set(cache_key, result)
    return result


# --- 87. Usage Analytics ---

def track_usage(event: str, details: str = "") -> None:
    """Track a usage event."""
    redis = _get_redis()
    if not redis:
        return
    try:
        data = redis.get(_USAGE_KEY)
        events = json.loads(data) if data else []
        events.append({
            "event": event,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(events) > 5000:
            events = events[-5000:]
        redis.set(_USAGE_KEY, json.dumps(events))
    except Exception:
        pass


def get_usage_stats() -> dict:
    """Get usage analytics summary."""
    redis = _get_redis()
    if not redis:
        return {"events": 0}

    try:
        data = redis.get(_USAGE_KEY)
        events = json.loads(data) if data else []

        # Count by event type
        by_type: dict[str, int] = {}
        for e in events:
            t = e.get("event", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "total_events": len(events),
            "by_type": by_type,
            "recent": events[-20:] if events else [],
        }
    except Exception:
        return {"events": 0}
