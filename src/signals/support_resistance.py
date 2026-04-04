"""Support and resistance level detection using pivot analysis and clustering."""

import numpy as np
import pandas as pd


def find_pivot_highs(df: pd.DataFrame, window: int = 5) -> list[dict]:
    """Detect pivot high points (local maxima in highs).

    A pivot high at index i means high[i] is the max within the surrounding window.
    """
    highs = df["high"].values
    pivots = []
    for i in range(window, len(highs) - window):
        if highs[i] == max(highs[i - window : i + window + 1]):
            pivots.append({
                "index": i,
                "price": float(highs[i]),
                "timestamp": df.index[i],
            })
    return pivots


def find_pivot_lows(df: pd.DataFrame, window: int = 5) -> list[dict]:
    """Detect pivot low points (local minima in lows)."""
    lows = df["low"].values
    pivots = []
    for i in range(window, len(lows) - window):
        if lows[i] == min(lows[i - window : i + window + 1]):
            pivots.append({
                "index": i,
                "price": float(lows[i]),
                "timestamp": df.index[i],
            })
    return pivots


def cluster_levels(levels: list[float], tolerance: float = 0.02) -> list[dict]:
    """Cluster nearby price levels into zones.

    Groups levels within `tolerance` (fraction) of each other.
    Returns list of clusters with average price, count, min, max.
    """
    if not levels:
        return []

    sorted_levels = sorted(levels)
    clusters: list[list[float]] = []
    current_cluster = [sorted_levels[0]]

    for price in sorted_levels[1:]:
        cluster_avg = sum(current_cluster) / len(current_cluster)
        if abs(price - cluster_avg) / cluster_avg <= tolerance:
            current_cluster.append(price)
        else:
            clusters.append(current_cluster)
            current_cluster = [price]
    clusters.append(current_cluster)

    result = []
    for cluster in clusters:
        avg = sum(cluster) / len(cluster)
        result.append({
            "price": round(avg, 2),
            "touches": len(cluster),
            "zone_top": round(max(cluster), 2),
            "zone_bottom": round(min(cluster), 2),
        })
    return result


def _score_level(level: dict, df: pd.DataFrame) -> float:
    """Score a level by touches and recency. Higher = stronger."""
    touches = level["touches"]
    total_bars = len(df)
    # Find most recent bar that touched this zone
    close = df["close"].values
    last_touch_dist = total_bars  # default: far away
    for i in range(total_bars - 1, -1, -1):
        if level["zone_bottom"] <= close[i] <= level["zone_top"]:
            last_touch_dist = total_bars - i
            break

    recency_bonus = max(0, 50 - last_touch_dist)  # more recent = higher bonus
    return touches * 15 + recency_bonus


def detect_support_resistance(
    df: pd.DataFrame, window: int = 5, min_touches: int = 2
) -> dict:
    """Detect support and resistance levels.

    Returns dict with "support" and "resistance" lists, each containing
    level dicts sorted by strength descending.
    """
    if len(df) < window * 3:
        return {"support": [], "resistance": []}

    pivot_highs = find_pivot_highs(df, window)
    pivot_lows = find_pivot_lows(df, window)

    last_close = float(df["close"].iloc[-1])
    atr_val = _simple_atr(df)

    # Cluster pivot prices
    high_prices = [p["price"] for p in pivot_highs]
    low_prices = [p["price"] for p in pivot_lows]
    all_prices = high_prices + low_prices

    # Use ATR-based tolerance for clustering
    tolerance = (atr_val / last_close) if last_close > 0 else 0.02
    tolerance = max(tolerance, 0.01)  # At least 1%

    clusters = cluster_levels(all_prices, tolerance)

    # Filter by minimum touches
    clusters = [c for c in clusters if c["touches"] >= min_touches]

    # Widen zones slightly using ATR
    zone_width = atr_val * 0.3
    for c in clusters:
        c["zone_top"] = round(c["zone_top"] + zone_width, 2)
        c["zone_bottom"] = round(c["zone_bottom"] - zone_width, 2)

    # Score each level
    for c in clusters:
        c["strength"] = round(_score_level(c, df), 1)

    # Split into support (below current price) and resistance (above)
    support = sorted(
        [c for c in clusters if c["price"] < last_close],
        key=lambda x: x["strength"],
        reverse=True,
    )
    resistance = sorted(
        [c for c in clusters if c["price"] >= last_close],
        key=lambda x: x["strength"],
        reverse=True,
    )

    # Add level_type
    for s in support:
        s["level_type"] = "support"
    for r in resistance:
        r["level_type"] = "resistance"

    return {
        "support": support[:5],
        "resistance": resistance[:5],
    }


def _simple_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Quick ATR calculation without ta dependency."""
    if len(df) < period + 1:
        return 0.0
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ),
    )
    return float(np.mean(tr[-period:]))
