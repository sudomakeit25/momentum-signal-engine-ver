"""Price projection: Fibonacci levels, pattern targets, trendline extensions."""

import numpy as np
import pandas as pd

from src.signals.support_resistance import find_pivot_highs, find_pivot_lows


def fibonacci_levels(df: pd.DataFrame) -> list[dict]:
    """Calculate Fibonacci retracement and extension levels from the most
    significant recent swing.

    Returns list of {price, confidence, reason, projection_type, estimated_days}.
    """
    if len(df) < 30:
        return []

    # Find the most significant recent swing
    pivots_high = find_pivot_highs(df, window=5)
    pivots_low = find_pivot_lows(df, window=5)

    if not pivots_high or not pivots_low:
        return []

    # Use the highest high and lowest low from recent pivots
    recent_high = max(pivots_high, key=lambda p: p["price"])
    recent_low = min(pivots_low, key=lambda p: p["price"])

    swing_range = recent_high["price"] - recent_low["price"]
    if swing_range <= 0:
        return []

    # Swing duration in bars — used to estimate timeframes
    swing_bars = abs(recent_high["index"] - recent_low["index"])

    last_close = float(df["close"].iloc[-1])
    projections = []

    def _estimate_days(target_price: float) -> int:
        """Estimate trading days based on distance relative to swing speed."""
        if swing_bars == 0 or swing_range == 0:
            return 20
        price_dist = abs(target_price - last_close)
        # Proportional: if swing covered X price in Y bars, target distance scales similarly
        days = int(price_dist / swing_range * swing_bars)
        return max(5, min(days, 120))  # clamp to 5-120 days

    # Determine if we're in an upswing or downswing
    if recent_high["index"] > recent_low["index"]:
        # Upswing: retracements are support levels, extensions are bullish targets
        fib_ratios = [
            (0.236, "Fib 23.6% retracement"),
            (0.382, "Fib 38.2% retracement"),
            (0.500, "Fib 50.0% retracement"),
            (0.618, "Fib 61.8% retracement"),
        ]
        for ratio, label in fib_ratios:
            price = recent_high["price"] - swing_range * ratio
            if price < last_close:
                projections.append({
                    "price": round(price, 2),
                    "confidence": 0.5 + (0.15 if ratio in (0.382, 0.618) else 0),
                    "reason": label,
                    "projection_type": "bearish",
                    "estimated_days": _estimate_days(price),
                })

        # Fibonacci extensions (bullish targets)
        extensions = [
            (1.272, "Fib 127.2% extension"),
            (1.618, "Fib 161.8% extension"),
        ]
        for ratio, label in extensions:
            price = recent_low["price"] + swing_range * ratio
            if price > last_close:
                projections.append({
                    "price": round(price, 2),
                    "confidence": 0.45,
                    "reason": label,
                    "projection_type": "bullish",
                    "estimated_days": _estimate_days(price),
                })
    else:
        # Downswing: retracements are resistance levels, extensions are bearish targets
        fib_ratios = [
            (0.236, "Fib 23.6% retracement"),
            (0.382, "Fib 38.2% retracement"),
            (0.500, "Fib 50.0% retracement"),
            (0.618, "Fib 61.8% retracement"),
        ]
        for ratio, label in fib_ratios:
            price = recent_low["price"] + swing_range * ratio
            if price > last_close:
                projections.append({
                    "price": round(price, 2),
                    "confidence": 0.5 + (0.15 if ratio in (0.382, 0.618) else 0),
                    "reason": label,
                    "projection_type": "bullish",
                    "estimated_days": _estimate_days(price),
                })

        extensions = [
            (1.272, "Fib 127.2% extension"),
            (1.618, "Fib 161.8% extension"),
        ]
        for ratio, label in extensions:
            price = recent_high["price"] - swing_range * ratio
            if price < last_close and price > 0:
                projections.append({
                    "price": round(price, 2),
                    "confidence": 0.45,
                    "reason": label,
                    "projection_type": "bearish",
                    "estimated_days": _estimate_days(price),
                })

    return projections


def project_price_zones(
    df: pd.DataFrame,
    patterns: list[dict],
    trendline_analysis: dict,
) -> list[dict]:
    """Combine all projection sources into a unified list of price targets.

    Returns list of {price, confidence, reason, projection_type}.
    """
    projections: list[dict] = []
    last_close = float(df["close"].iloc[-1])

    # 1. Pattern-based targets
    for pattern in patterns:
        if pattern.get("target_price"):
            is_bullish = pattern["target_price"] > last_close
            # Estimate: pattern width (boundary time span) ≈ time to reach target
            bp = pattern.get("boundary_points", [])
            if len(bp) >= 2:
                first_idx = next((i for i, row in enumerate(df.index)
                                  if str(row)[:10] >= str(bp[0].get("time", ""))[:10]), 0)
                last_idx = next((i for i, row in enumerate(df.index)
                                 if str(row)[:10] >= str(bp[-1].get("time", ""))[:10]), len(df) - 1)
                pattern_width = max(last_idx - first_idx, 10)
            else:
                pattern_width = 20
            projections.append({
                "price": pattern["target_price"],
                "confidence": pattern["confidence"],
                "reason": f"{pattern['pattern_type'].replace('_', ' ').title()} target",
                "projection_type": "bullish" if is_bullish else "bearish",
                "estimated_days": min(pattern_width, 90),
            })

    # 2. Trendline projection endpoints (always 10 bars ahead)
    for line in trendline_analysis.get("uptrends", []):
        if line.get("projection"):
            last_proj = line["projection"][-1]
            projections.append({
                "price": last_proj["price"],
                "confidence": min(0.3 + line["touches"] * 0.1, 0.7),
                "reason": f"Uptrend projection ({line['touches']} touches)",
                "projection_type": "bullish",
                "estimated_days": len(line["projection"]),
            })

    for line in trendline_analysis.get("downtrends", []):
        if line.get("projection"):
            last_proj = line["projection"][-1]
            if last_proj["price"] > 0:
                projections.append({
                    "price": last_proj["price"],
                    "confidence": min(0.3 + line["touches"] * 0.1, 0.7),
                    "reason": f"Downtrend projection ({line['touches']} touches)",
                    "projection_type": "bearish",
                    "estimated_days": len(line["projection"]),
                })

    # 3. Fibonacci levels
    fib_projs = fibonacci_levels(df)
    projections.extend(fib_projs)

    # Deduplicate close targets (within 1%)
    projections = _deduplicate_projections(projections)

    # Sort by confidence
    projections.sort(key=lambda p: p["confidence"], reverse=True)

    # Limit to top 6
    return projections[:6]


def _deduplicate_projections(
    projections: list[dict], tolerance: float = 0.01
) -> list[dict]:
    """Remove projections at very similar price levels, keeping higher confidence."""
    if not projections:
        return []

    projections.sort(key=lambda p: p["confidence"], reverse=True)
    kept = []
    for proj in projections:
        is_dup = False
        for existing in kept:
            if existing["price"] > 0:
                diff = abs(proj["price"] - existing["price"]) / existing["price"]
                if diff < tolerance:
                    is_dup = True
                    break
        if not is_dup:
            kept.append(proj)
    return kept
