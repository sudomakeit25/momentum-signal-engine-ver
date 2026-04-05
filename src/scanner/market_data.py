"""Market data features: insider aggregator, IPO tracker, dividends,
stock splits, Fibonacci, volume profile.

Features requiring FMP gracefully return empty when key is not configured.
"""

import logging
import numpy as np
import pandas as pd

from src.data import client as alpaca_client
from src.data.cache import Cache
from src.data.fmp_client import _get as fmp_get

logger = logging.getLogger("mse.market_data")
_cache = Cache()


# --- 5. Insider Buying Aggregator ---

def get_insider_aggregation() -> dict:
    """Aggregate insider buys across all sectors."""
    cache_key = "insider_aggregation"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    from src.scanner.sectors import SECTORS

    data = fmp_get("/v4/insider-trading", {"limit": 100, "transactionType": "P-Purchase"}, cache_key="fmp_insider_agg")
    if not data:
        return {"total_buys": 0, "sectors": {}, "top_buyers": []}

    # Aggregate by sector
    from src.scanner.sectors import get_sector
    sector_buys: dict[str, dict] = {}
    top_buyers = []

    for trade in data[:100]:
        sym = trade.get("symbol", "")
        sector = get_sector(sym)
        shares = abs(trade.get("securitiesTransacted", 0))
        price = trade.get("price", 0) or 0
        value = shares * price

        if sector not in sector_buys:
            sector_buys[sector] = {"count": 0, "total_value": 0, "symbols": set()}
        sector_buys[sector]["count"] += 1
        sector_buys[sector]["total_value"] += value
        sector_buys[sector]["symbols"].add(sym)

        if value > 100_000:
            top_buyers.append({
                "symbol": sym,
                "insider": trade.get("reportingName", "Unknown"),
                "shares": int(shares),
                "value": round(value, 0),
                "date": trade.get("filingDate", ""),
            })

    # Convert sets to lists for JSON
    for s in sector_buys.values():
        s["symbols"] = list(s["symbols"])
        s["total_value"] = round(s["total_value"], 0)

    result = {
        "total_buys": len(data),
        "sectors": sector_buys,
        "top_buyers": sorted(top_buyers, key=lambda x: x["value"], reverse=True)[:20],
    }
    _cache.set(cache_key, result)
    return result


# --- 6. IPO Tracker ---

def get_ipo_calendar() -> list[dict]:
    """Get upcoming and recent IPOs."""
    cache_key = "ipo_calendar"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    data = fmp_get("/v3/ipo_calendar", cache_key="fmp_ipo")
    if not data:
        return []

    results = [
        {
            "symbol": item.get("symbol", ""),
            "company": item.get("company", ""),
            "date": item.get("date", ""),
            "exchange": item.get("exchange", ""),
            "price_range": item.get("priceRange", ""),
            "shares": item.get("shares", 0),
        }
        for item in data[:30]
        if item.get("symbol")
    ]
    if results:
        _cache.set(cache_key, results)
    return results


# --- 7. Dividend Calendar ---

def get_dividend_calendar() -> list[dict]:
    """Get upcoming dividend dates."""
    cache_key = "dividend_calendar"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    from datetime import datetime, timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    data = fmp_get("/v3/stock_dividend_calendar", {"from": today, "to": end}, cache_key="fmp_div")
    if not data:
        return []

    results = [
        {
            "symbol": item.get("symbol", ""),
            "date": item.get("date", ""),
            "dividend": item.get("dividend", 0),
            "adj_dividend": item.get("adjDividend", 0),
            "record_date": item.get("recordDate", ""),
            "payment_date": item.get("paymentDate", ""),
        }
        for item in data[:50]
        if item.get("symbol")
    ]
    if results:
        _cache.set(cache_key, results)
    return results


# --- 8. Stock Split Tracker ---

def get_stock_splits() -> list[dict]:
    """Get upcoming and recent stock splits."""
    cache_key = "stock_splits"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    from datetime import datetime, timedelta
    today = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")

    data = fmp_get("/v3/stock_split_calendar", {"from": today, "to": end}, cache_key="fmp_splits")
    if not data:
        return []

    results = [
        {
            "symbol": item.get("symbol", ""),
            "date": item.get("date", ""),
            "numerator": item.get("numerator", 0),
            "denominator": item.get("denominator", 0),
            "ratio": f"{item.get('numerator', 0)}:{item.get('denominator', 0)}",
        }
        for item in data[:30]
        if item.get("symbol")
    ]
    if results:
        _cache.set(cache_key, results)
    return results


# --- 11. Fibonacci Retracement ---

def calculate_fibonacci(symbol: str, days: int = 60) -> dict:
    """Calculate Fibonacci retracement levels."""
    try:
        df = alpaca_client.get_bars(symbol, days=days)
        if df is None or len(df) < 20:
            return {"symbol": symbol, "error": "Insufficient data"}

        high = float(df["high"].max())
        low = float(df["low"].min())
        current = float(df["close"].iloc[-1])
        diff = high - low

        # Determine trend direction
        mid_price = float(df["close"].iloc[len(df)//2])
        uptrend = current > mid_price

        levels = {
            "0.0": round(high if uptrend else low, 2),
            "0.236": round(high - 0.236 * diff if uptrend else low + 0.236 * diff, 2),
            "0.382": round(high - 0.382 * diff if uptrend else low + 0.382 * diff, 2),
            "0.5": round(high - 0.5 * diff if uptrend else low + 0.5 * diff, 2),
            "0.618": round(high - 0.618 * diff if uptrend else low + 0.618 * diff, 2),
            "0.786": round(high - 0.786 * diff if uptrend else low + 0.786 * diff, 2),
            "1.0": round(low if uptrend else high, 2),
        }

        # Find nearest level
        nearest = min(levels.items(), key=lambda x: abs(x[1] - current))

        return {
            "symbol": symbol,
            "trend": "uptrend" if uptrend else "downtrend",
            "high": round(high, 2),
            "low": round(low, 2),
            "current": round(current, 2),
            "levels": levels,
            "nearest_level": nearest[0],
            "nearest_price": nearest[1],
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


# --- 12. Volume Profile ---

def calculate_volume_profile(symbol: str, bins: int = 20) -> dict:
    """Calculate price-by-volume profile."""
    try:
        df = alpaca_client.get_bars(symbol, days=60)
        if df is None or len(df) < 20:
            return {"symbol": symbol, "error": "Insufficient data"}

        prices = df["close"].values
        volumes = df["volume"].values
        current = float(df["close"].iloc[-1])

        price_min = float(prices.min())
        price_max = float(prices.max())
        bin_edges = np.linspace(price_min, price_max, bins + 1)

        profile = []
        max_vol = 0
        poc_price = 0  # Point of Control

        for i in range(bins):
            mask = (prices >= bin_edges[i]) & (prices < bin_edges[i + 1])
            vol = float(volumes[mask].sum())
            mid = (bin_edges[i] + bin_edges[i + 1]) / 2
            profile.append({
                "price_low": round(float(bin_edges[i]), 2),
                "price_high": round(float(bin_edges[i + 1]), 2),
                "price_mid": round(mid, 2),
                "volume": int(vol),
            })
            if vol > max_vol:
                max_vol = vol
                poc_price = mid

        # Value area (70% of volume around POC)
        total_vol = sum(p["volume"] for p in profile)
        sorted_profile = sorted(profile, key=lambda p: p["volume"], reverse=True)
        cumulative = 0
        va_prices = []
        for p in sorted_profile:
            cumulative += p["volume"]
            va_prices.append(p["price_mid"])
            if cumulative >= total_vol * 0.7:
                break

        return {
            "symbol": symbol,
            "current": round(current, 2),
            "poc": round(poc_price, 2),
            "value_area_high": round(max(va_prices), 2) if va_prices else 0,
            "value_area_low": round(min(va_prices), 2) if va_prices else 0,
            "profile": profile,
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


# --- 13. Ichimoku Cloud ---

def calculate_ichimoku(symbol: str) -> dict:
    """Calculate Ichimoku cloud components."""
    try:
        df = alpaca_client.get_bars(symbol, days=100)
        if df is None or len(df) < 52:
            return {"symbol": symbol, "error": "Insufficient data"}

        high = df["high"]
        low = df["low"]
        close = df["close"]

        tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
        kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
        chikou = close.shift(-26)

        current = float(close.iloc[-1])
        cloud_top = max(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))
        cloud_bottom = min(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))

        if current > cloud_top:
            signal = "bullish"
        elif current < cloud_bottom:
            signal = "bearish"
        else:
            signal = "in_cloud"

        return {
            "symbol": symbol,
            "current": round(current, 2),
            "tenkan": round(float(tenkan.iloc[-1]), 2),
            "kijun": round(float(kijun.iloc[-1]), 2),
            "senkou_a": round(float(senkou_a.iloc[-1]), 2) if pd.notna(senkou_a.iloc[-1]) else None,
            "senkou_b": round(float(senkou_b.iloc[-1]), 2) if pd.notna(senkou_b.iloc[-1]) else None,
            "cloud_top": round(cloud_top, 2),
            "cloud_bottom": round(cloud_bottom, 2),
            "signal": signal,
            "tk_cross": "bullish" if float(tenkan.iloc[-1]) > float(kijun.iloc[-1]) else "bearish",
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}
