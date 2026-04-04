"""Trendline detection and projection using swing point analysis."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.signals.support_resistance import find_pivot_highs, find_pivot_lows


def detect_uptrend_lines(
    df: pd.DataFrame, min_touches: int = 2, tolerance: float = 0.015
) -> list[dict]:
    """Detect uptrend lines connecting higher lows.

    Returns list of trendline dicts with start/end points, slope, and touch count.
    """
    pivots = find_pivot_lows(df, window=5)
    if len(pivots) < 2:
        return []

    lines = []
    n = len(pivots)

    for i in range(n - 1):
        for j in range(i + 1, min(i + 8, n)):  # limit combos for performance
            p1 = pivots[i]
            p2 = pivots[j]

            # Must be rising (higher lows)
            if p2["price"] <= p1["price"]:
                continue

            # Calculate line slope
            dx = p2["index"] - p1["index"]
            if dx == 0:
                continue
            slope = (p2["price"] - p1["price"]) / dx
            intercept = p1["price"] - slope * p1["index"]

            # Count touches
            touches = 0
            for pivot in pivots:
                expected = slope * pivot["index"] + intercept
                if abs(pivot["price"] - expected) / expected <= tolerance:
                    touches += 1

            if touches >= min_touches:
                lines.append({
                    "start_idx": p1["index"],
                    "end_idx": p2["index"],
                    "start_price": p1["price"],
                    "end_price": p2["price"],
                    "start_time": p1["timestamp"],
                    "end_time": p2["timestamp"],
                    "slope": slope,
                    "intercept": intercept,
                    "touches": touches,
                    "trend_type": "uptrend",
                })

    # Deduplicate: keep lines with most touches, remove similar ones
    lines.sort(key=lambda x: x["touches"], reverse=True)
    return _deduplicate_lines(lines)[:3]


def detect_downtrend_lines(
    df: pd.DataFrame, min_touches: int = 2, tolerance: float = 0.015
) -> list[dict]:
    """Detect downtrend lines connecting lower highs."""
    pivots = find_pivot_highs(df, window=5)
    if len(pivots) < 2:
        return []

    lines = []
    n = len(pivots)

    for i in range(n - 1):
        for j in range(i + 1, min(i + 8, n)):
            p1 = pivots[i]
            p2 = pivots[j]

            # Must be falling (lower highs)
            if p2["price"] >= p1["price"]:
                continue

            dx = p2["index"] - p1["index"]
            if dx == 0:
                continue
            slope = (p2["price"] - p1["price"]) / dx
            intercept = p1["price"] - slope * p1["index"]

            touches = 0
            for pivot in pivots:
                expected = slope * pivot["index"] + intercept
                if expected > 0 and abs(pivot["price"] - expected) / expected <= tolerance:
                    touches += 1

            if touches >= min_touches:
                lines.append({
                    "start_idx": p1["index"],
                    "end_idx": p2["index"],
                    "start_price": p1["price"],
                    "end_price": p2["price"],
                    "start_time": p1["timestamp"],
                    "end_time": p2["timestamp"],
                    "slope": slope,
                    "intercept": intercept,
                    "touches": touches,
                    "trend_type": "downtrend",
                })

    lines.sort(key=lambda x: x["touches"], reverse=True)
    return _deduplicate_lines(lines)[:3]


def _deduplicate_lines(lines: list[dict], slope_tol: float = 0.3) -> list[dict]:
    """Remove similar trendlines, keeping ones with most touches."""
    if not lines:
        return []
    kept = [lines[0]]
    for line in lines[1:]:
        is_dup = False
        for existing in kept:
            if existing["slope"] == 0:
                continue
            slope_ratio = abs(line["slope"] / existing["slope"]) if existing["slope"] != 0 else 999
            if abs(1 - slope_ratio) < slope_tol:
                # Check if intercepts are close too
                price_diff = abs(line["intercept"] - existing["intercept"])
                avg_price = abs(existing["intercept"]) or 1
                if price_diff / avg_price < 0.05:
                    is_dup = True
                    break
        if not is_dup:
            kept.append(line)
    return kept


def project_trendline(
    line: dict, df: pd.DataFrame, periods_ahead: int = 10
) -> list[dict]:
    """Project a trendline forward N periods.

    Returns list of {time, price} points for the projection.
    """
    last_idx = len(df) - 1
    slope = line["slope"]
    intercept = line["intercept"]

    # Estimate time step from the last few bars
    if hasattr(df.index[-1], "to_pydatetime"):
        last_time = df.index[-1].to_pydatetime()
    else:
        last_time = pd.Timestamp(df.index[-1]).to_pydatetime()

    if len(df) > 1:
        if hasattr(df.index[-2], "to_pydatetime"):
            prev_time = df.index[-2].to_pydatetime()
        else:
            prev_time = pd.Timestamp(df.index[-2]).to_pydatetime()
        time_step = last_time - prev_time
    else:
        time_step = timedelta(days=1)

    projection = []
    for step in range(1, periods_ahead + 1):
        idx = last_idx + step
        price = slope * idx + intercept
        if price <= 0:
            break
        proj_time = last_time + time_step * step
        projection.append({
            "time": proj_time.isoformat(),
            "price": round(float(price), 2),
        })

    return projection


def analyze_trendlines(df: pd.DataFrame) -> dict:
    """Main function: detect all trendlines and determine dominant trend.

    Returns dict with uptrends, downtrends, and dominant_trend.
    """
    if len(df) < 30:
        return {"uptrends": [], "downtrends": [], "dominant_trend": "neutral"}

    uptrends = detect_uptrend_lines(df)
    downtrends = detect_downtrend_lines(df)

    # Add projections
    for line in uptrends:
        line["projection"] = project_trendline(line, df, 10)
    for line in downtrends:
        line["projection"] = project_trendline(line, df, 10)

    # Determine dominant trend based on recent price action
    # Check which trendlines extend through the most recent bars
    last_idx = len(df) - 1
    recent_up_touches = sum(
        1 for line in uptrends if line["end_idx"] > last_idx - 20
    )
    recent_down_touches = sum(
        1 for line in downtrends if line["end_idx"] > last_idx - 20
    )

    if recent_up_touches > recent_down_touches:
        dominant = "bullish"
    elif recent_down_touches > recent_up_touches:
        dominant = "bearish"
    else:
        dominant = "neutral"

    return {
        "uptrends": uptrends,
        "downtrends": downtrends,
        "dominant_trend": dominant,
    }
