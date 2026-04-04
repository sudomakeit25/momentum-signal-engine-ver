"""Advanced chart pattern detection: H&S, double top/bottom, triangles, etc."""

import numpy as np
import pandas as pd

from src.signals.support_resistance import find_pivot_highs, find_pivot_lows


def detect_head_and_shoulders(df: pd.DataFrame) -> list[dict]:
    """Detect head and shoulders (bearish reversal).

    Requires: left shoulder peak, higher head peak, right shoulder peak at similar
    height to left shoulder, with neckline connecting the troughs.
    Returns all instances found.
    """
    pivots = find_pivot_highs(df, window=5)
    if len(pivots) < 3:
        return []

    # Look for the pattern in the last 80 bars
    recent = [p for p in pivots if p["index"] > len(df) - 80]
    if len(recent) < 3:
        return []

    results = []
    used_heads: set[int] = set()

    # Try combinations of 3 peaks
    for i in range(len(recent) - 2):
        ls, head, rs = recent[i], recent[i + 1], recent[i + 2]

        if head["index"] in used_heads:
            continue

        # Head must be highest
        if head["price"] <= ls["price"] or head["price"] <= rs["price"]:
            continue

        # Shoulders should be at similar height (within 5%)
        avg_shoulder = (ls["price"] + rs["price"]) / 2
        if abs(ls["price"] - rs["price"]) / avg_shoulder > 0.05:
            continue

        # Head should be at least 3% higher than shoulders
        if (head["price"] - avg_shoulder) / avg_shoulder < 0.03:
            continue

        # Find neckline (troughs between shoulders and head)
        trough1_price = float(df["low"].iloc[ls["index"]:head["index"]].min())
        trough2_price = float(df["low"].iloc[head["index"]:rs["index"]].min())
        neckline = (trough1_price + trough2_price) / 2

        # Measured move target
        pattern_height = head["price"] - neckline
        target = neckline - pattern_height

        # Confidence based on symmetry
        shoulder_diff = abs(ls["price"] - rs["price"]) / avg_shoulder
        confidence = max(0.5, 0.85 - shoulder_diff * 5)

        used_heads.add(head["index"])
        results.append({
            "pattern_type": "head_and_shoulders",
            "confidence": round(confidence, 2),
            "target_price": round(target, 2),
            "bias": "bearish",
            "boundary_points": [
                {"time": ls["timestamp"].isoformat(), "price": ls["price"]},
                {"time": df.index[ls["index"] + (head["index"] - ls["index"]) // 2].isoformat(), "price": trough1_price},
                {"time": head["timestamp"].isoformat(), "price": head["price"]},
                {"time": df.index[head["index"] + (rs["index"] - head["index"]) // 2].isoformat(), "price": trough2_price},
                {"time": rs["timestamp"].isoformat(), "price": rs["price"]},
            ],
            "description": f"Head & Shoulders: neckline at ${neckline:.2f}, bearish target ${target:.2f}. Head at ${head['price']:.2f} with shoulders at ~${avg_shoulder:.2f}.",
        })

    return results


def detect_inverse_head_and_shoulders(df: pd.DataFrame) -> list[dict]:
    """Detect inverse head and shoulders (bullish reversal). Returns all instances."""
    pivots = find_pivot_lows(df, window=5)
    if len(pivots) < 3:
        return []

    recent = [p for p in pivots if p["index"] > len(df) - 80]
    if len(recent) < 3:
        return []

    results = []
    used_heads: set[int] = set()

    for i in range(len(recent) - 2):
        ls, head, rs = recent[i], recent[i + 1], recent[i + 2]

        if head["index"] in used_heads:
            continue

        # Head must be lowest
        if head["price"] >= ls["price"] or head["price"] >= rs["price"]:
            continue

        avg_shoulder = (ls["price"] + rs["price"]) / 2
        if abs(ls["price"] - rs["price"]) / avg_shoulder > 0.05:
            continue

        if (avg_shoulder - head["price"]) / avg_shoulder < 0.03:
            continue

        peak1_price = float(df["high"].iloc[ls["index"]:head["index"]].max())
        peak2_price = float(df["high"].iloc[head["index"]:rs["index"]].max())
        neckline = (peak1_price + peak2_price) / 2

        pattern_height = neckline - head["price"]
        target = neckline + pattern_height

        shoulder_diff = abs(ls["price"] - rs["price"]) / avg_shoulder
        confidence = max(0.5, 0.85 - shoulder_diff * 5)

        used_heads.add(head["index"])
        results.append({
            "pattern_type": "inverse_head_and_shoulders",
            "confidence": round(confidence, 2),
            "target_price": round(target, 2),
            "bias": "bullish",
            "boundary_points": [
                {"time": ls["timestamp"].isoformat(), "price": ls["price"]},
                {"time": df.index[ls["index"] + (head["index"] - ls["index"]) // 2].isoformat(), "price": peak1_price},
                {"time": head["timestamp"].isoformat(), "price": head["price"]},
                {"time": df.index[head["index"] + (rs["index"] - head["index"]) // 2].isoformat(), "price": peak2_price},
                {"time": rs["timestamp"].isoformat(), "price": rs["price"]},
            ],
            "description": f"Inverse H&S: neckline at ${neckline:.2f}, bullish target ${target:.2f}. Bullish reversal pattern.",
        })

    return results


def detect_double_top(df: pd.DataFrame, tolerance: float = 0.03) -> list[dict]:
    """Detect double top (bearish reversal). Returns all instances.

    Two peaks at similar price separated by a trough.
    """
    pivots = find_pivot_highs(df, window=5)
    recent = [p for p in pivots if p["index"] > len(df) - 60]
    if len(recent) < 2:
        return []

    results = []
    used_pivots: set[int] = set()

    for i in range(len(recent) - 1):
        p1, p2 = recent[i], recent[i + 1]

        if p1["index"] in used_pivots or p2["index"] in used_pivots:
            continue

        avg_peak = (p1["price"] + p2["price"]) / 2

        # Peaks must be at similar height
        if abs(p1["price"] - p2["price"]) / avg_peak > tolerance:
            continue

        # Need some separation (at least 10 bars)
        if p2["index"] - p1["index"] < 10:
            continue

        # Find trough between peaks
        trough_price = float(df["low"].iloc[p1["index"]:p2["index"]].min())

        # Trough should be at least 3% below peaks
        if (avg_peak - trough_price) / avg_peak < 0.03:
            continue

        target = trough_price - (avg_peak - trough_price)

        used_pivots.add(p1["index"])
        used_pivots.add(p2["index"])
        results.append({
            "pattern_type": "double_top",
            "confidence": 0.70,
            "target_price": round(target, 2),
            "bias": "bearish",
            "boundary_points": [
                {"time": p1["timestamp"].isoformat(), "price": p1["price"]},
                {"time": df.index[(p1["index"] + p2["index"]) // 2].isoformat(), "price": trough_price},
                {"time": p2["timestamp"].isoformat(), "price": p2["price"]},
            ],
            "description": f"Double Top at ~${avg_peak:.2f} with support at ${trough_price:.2f}. Bearish target ${target:.2f}.",
        })

    return results


def detect_double_bottom(df: pd.DataFrame, tolerance: float = 0.03) -> list[dict]:
    """Detect double bottom (bullish reversal). Returns all instances."""
    pivots = find_pivot_lows(df, window=5)
    recent = [p for p in pivots if p["index"] > len(df) - 60]
    if len(recent) < 2:
        return []

    results = []
    used_pivots: set[int] = set()

    for i in range(len(recent) - 1):
        p1, p2 = recent[i], recent[i + 1]

        if p1["index"] in used_pivots or p2["index"] in used_pivots:
            continue

        avg_low = (p1["price"] + p2["price"]) / 2

        if abs(p1["price"] - p2["price"]) / avg_low > tolerance:
            continue

        if p2["index"] - p1["index"] < 10:
            continue

        peak_price = float(df["high"].iloc[p1["index"]:p2["index"]].max())

        if (peak_price - avg_low) / avg_low < 0.03:
            continue

        target = peak_price + (peak_price - avg_low)

        used_pivots.add(p1["index"])
        used_pivots.add(p2["index"])
        results.append({
            "pattern_type": "double_bottom",
            "confidence": 0.70,
            "target_price": round(target, 2),
            "bias": "bullish",
            "boundary_points": [
                {"time": p1["timestamp"].isoformat(), "price": p1["price"]},
                {"time": df.index[(p1["index"] + p2["index"]) // 2].isoformat(), "price": peak_price},
                {"time": p2["timestamp"].isoformat(), "price": p2["price"]},
            ],
            "description": f"Double Bottom at ~${avg_low:.2f} with resistance at ${peak_price:.2f}. Bullish target ${target:.2f}.",
        })

    return results


def detect_triangle(df: pd.DataFrame) -> list[dict]:
    """Detect ascending, descending, or symmetrical triangle.

    Scans multiple window sizes to find triangles at different scales.
    """
    if len(df) < 40:
        return []

    results = []
    # Scan at multiple window sizes to catch triangles at different scales
    windows = [w for w in [30, 50, 70] if w < len(df) - 10]

    for window in windows:
        recent_df = df.iloc[-window:]
        highs = find_pivot_highs(recent_df, window=3)
        lows = find_pivot_lows(recent_df, window=3)

        if len(highs) < 2 or len(lows) < 2:
            continue

        high_indices = np.array([p["index"] for p in highs])
        high_prices = np.array([p["price"] for p in highs])
        low_indices = np.array([p["index"] for p in lows])
        low_prices = np.array([p["price"] for p in lows])

        if len(high_indices) < 2 or len(low_indices) < 2:
            continue

        high_slope = np.polyfit(high_indices, high_prices, 1)[0]
        low_slope = np.polyfit(low_indices, low_prices, 1)[0]

        avg_price = float(df["close"].iloc[-1])
        high_slope_pct = high_slope / avg_price
        low_slope_pct = low_slope / avg_price

        pattern_type = None
        description = ""
        bias = "neutral"

        if abs(high_slope_pct) < 0.001 and low_slope_pct > 0.0005:
            pattern_type = "ascending_triangle"
            bias = "bullish"
            description = "Ascending Triangle: flat resistance with rising support. Bullish breakout expected."
        elif high_slope_pct < -0.0005 and abs(low_slope_pct) < 0.001:
            pattern_type = "descending_triangle"
            bias = "bearish"
            description = "Descending Triangle: falling highs with flat support. Bearish breakdown likely."
        elif high_slope_pct < -0.0003 and low_slope_pct > 0.0003:
            pattern_type = "symmetrical_triangle"
            bias = "neutral"
            description = "Symmetrical Triangle: converging highs and lows. Breakout direction uncertain."
        else:
            continue

        # Skip if we already found this triangle type
        if any(r["pattern_type"] == pattern_type for r in results):
            continue

        range_start = max(high_prices[0], low_prices[0]) - min(high_prices[0], low_prices[0])

        if pattern_type == "ascending_triangle":
            breakout_level = float(max(high_prices))
            target = breakout_level + range_start
        elif pattern_type == "descending_triangle":
            breakout_level = float(min(low_prices))
            target = breakout_level - range_start
        else:
            target = None

        boundary = []
        for p in highs:
            boundary.append({"time": p["timestamp"].isoformat(), "price": p["price"]})
        for p in reversed(lows):
            boundary.append({"time": p["timestamp"].isoformat(), "price": p["price"]})

        results.append({
            "pattern_type": pattern_type,
            "confidence": 0.65,
            "target_price": round(target, 2) if target else None,
            "bias": bias,
            "boundary_points": boundary,
            "description": description + (f" Target: ${target:.2f}" if target else ""),
        })

    return results


def detect_cup_and_handle(df: pd.DataFrame) -> list[dict]:
    """Detect cup and handle pattern (bullish continuation).

    Scans multiple lookback windows. Cup: U-shaped consolidation. Handle: small pullback.
    """
    results = []

    for lookback in [50, 60, 80]:
        if len(df) < lookback + 10:
            continue

        window = df.iloc[-lookback:]
        closes = window["close"].values

        # Cup: left rim high, dip, right rim back near left rim
        left_max_idx = np.argmax(closes[:lookback // 3])
        left_max = closes[left_max_idx]

        # Find cup bottom (minimum in middle section)
        mid_start = lookback // 4
        mid_end = lookback * 3 // 4
        cup_bottom_idx = mid_start + np.argmin(closes[mid_start:mid_end])
        cup_bottom = closes[cup_bottom_idx]

        # Cup depth should be 8-40% of price
        cup_depth_pct = (left_max - cup_bottom) / left_max
        if cup_depth_pct < 0.08 or cup_depth_pct > 0.40:
            continue

        # Right rim should be within 5% of left rim
        right_section = closes[mid_end:]
        if len(right_section) == 0:
            continue
        right_max = float(np.max(right_section))
        if abs(right_max - left_max) / left_max > 0.05:
            continue

        # Handle: small pullback at the end (last 5-15 bars)
        handle = closes[-15:]
        handle_high = float(np.max(handle))
        handle_low = float(np.min(handle))
        handle_depth = (handle_high - handle_low) / handle_high

        # Handle should be shallow (< half the cup depth)
        if handle_depth > cup_depth_pct * 0.6:
            continue

        breakout_level = right_max
        target = breakout_level + (breakout_level - cup_bottom)

        # Skip if too similar to an already-found cup & handle
        if any(
            r["pattern_type"] == "cup_and_handle"
            and abs(r["target_price"] - round(target, 2)) / target < 0.02
            for r in results
        ):
            continue

        boundary = [
            {"time": window.index[left_max_idx].isoformat(), "price": float(left_max)},
            {"time": window.index[cup_bottom_idx].isoformat(), "price": float(cup_bottom)},
            {"time": window.index[mid_end + np.argmax(right_section)].isoformat(), "price": right_max},
        ]

        results.append({
            "pattern_type": "cup_and_handle",
            "confidence": 0.70,
            "target_price": round(target, 2),
            "bias": "bullish",
            "boundary_points": boundary,
            "description": f"Cup & Handle ({lookback}d): rim at ${breakout_level:.2f}, cup depth {cup_depth_pct*100:.0f}%. Bullish target ${target:.2f}.",
        })

    return results


def detect_wedge(df: pd.DataFrame) -> list[dict]:
    """Detect rising wedge (bearish) or falling wedge (bullish).

    Scans multiple window sizes.
    """
    if len(df) < 30:
        return []

    results = []
    found_types: set[str] = set()

    for window in [30, 40, 55]:
        if window >= len(df) - 10:
            continue

        recent_df = df.iloc[-window:]
        highs = find_pivot_highs(recent_df, window=3)
        lows = find_pivot_lows(recent_df, window=3)

        if len(highs) < 2 or len(lows) < 2:
            continue

        high_indices = np.array([p["index"] for p in highs])
        high_prices = np.array([p["price"] for p in highs])
        low_indices = np.array([p["index"] for p in lows])
        low_prices = np.array([p["price"] for p in lows])

        high_slope = np.polyfit(high_indices, high_prices, 1)[0]
        low_slope = np.polyfit(low_indices, low_prices, 1)[0]

        avg_price = float(df["close"].iloc[-1])
        h_pct = high_slope / avg_price
        l_pct = low_slope / avg_price

        # Rising wedge
        if h_pct > 0.0003 and l_pct > 0.0003 and l_pct > h_pct and "rising_wedge" not in found_types:
            pattern_range = high_prices[-1] - low_prices[-1]
            target = float(low_prices[-1]) - pattern_range
            found_types.add("rising_wedge")
            results.append({
                "pattern_type": "rising_wedge",
                "confidence": 0.60,
                "target_price": round(target, 2),
                "bias": "bearish",
                "boundary_points": [
                    {"time": highs[0]["timestamp"].isoformat(), "price": highs[0]["price"]},
                    {"time": highs[-1]["timestamp"].isoformat(), "price": highs[-1]["price"]},
                    {"time": lows[-1]["timestamp"].isoformat(), "price": lows[-1]["price"]},
                    {"time": lows[0]["timestamp"].isoformat(), "price": lows[0]["price"]},
                ],
                "description": f"Rising Wedge ({window}d): bearish, both highs and lows rising but converging. Target ${target:.2f}.",
            })

        # Falling wedge
        if h_pct < -0.0003 and l_pct < -0.0003 and h_pct < l_pct and "falling_wedge" not in found_types:
            pattern_range = high_prices[-1] - low_prices[-1]
            target = float(high_prices[-1]) + pattern_range
            found_types.add("falling_wedge")
            results.append({
                "pattern_type": "falling_wedge",
                "confidence": 0.60,
                "target_price": round(target, 2),
                "bias": "bullish",
                "boundary_points": [
                    {"time": highs[0]["timestamp"].isoformat(), "price": highs[0]["price"]},
                    {"time": highs[-1]["timestamp"].isoformat(), "price": highs[-1]["price"]},
                    {"time": lows[-1]["timestamp"].isoformat(), "price": lows[-1]["price"]},
                    {"time": lows[0]["timestamp"].isoformat(), "price": lows[0]["price"]},
                ],
                "description": f"Falling Wedge ({window}d): bullish, both highs and lows falling but converging. Target ${target:.2f}.",
            })

    return results


def detect_all_patterns(df: pd.DataFrame) -> list[dict]:
    """Run all pattern detectors and return list of found patterns.

    Each detector can return multiple instances of its pattern type.
    """
    if len(df) < 30:
        return []

    patterns = []

    detectors = [
        detect_head_and_shoulders,
        detect_inverse_head_and_shoulders,
        detect_double_top,
        detect_double_bottom,
        detect_triangle,
        detect_cup_and_handle,
        detect_wedge,
    ]

    for detector in detectors:
        try:
            results = detector(df)
            patterns.extend(results)
        except Exception:
            continue

    # Sort by confidence
    patterns.sort(key=lambda p: p["confidence"], reverse=True)
    return patterns
