"""Dark pool / short volume analysis.

Detects accumulation and distribution patterns by analyzing FINRA short
sale volume data relative to price action.
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from src.data import client as alpaca_client
from src.data.finra_client import get_short_volume, get_short_volume_batch
from src.data.models import DarkPoolEntry, DarkPoolResult

logger = logging.getLogger("mse.dark_pool")


def analyze_symbol(symbol: str, days: int = 20) -> DarkPoolResult | None:
    """Analyze dark pool activity for a single symbol."""
    entries_raw = get_short_volume(symbol, days=days)
    if len(entries_raw) < 5:
        return None

    # Get price data for the same period
    price_df = alpaca_client.get_bars(symbol, days=days + 30)
    if price_df is None or price_df.empty:
        return None

    entries = [
        DarkPoolEntry(
            symbol=symbol,
            date=datetime.fromisoformat(e["date"]),
            short_volume=e["short_volume"],
            short_exempt_volume=e["short_exempt_volume"],
            total_volume=e["total_volume"],
            short_pct=e["short_pct"],
        )
        for e in entries_raw
    ]

    short_pcts = [e.short_pct for e in entries]
    avg_short_pct = round(np.mean(short_pcts), 2)
    recent_short_pct = round(np.mean(short_pcts[-5:]), 2) if len(short_pcts) >= 5 else avg_short_pct

    # Price change over the period
    if len(price_df) >= 2:
        start_price = price_df["close"].iloc[-min(len(entries), len(price_df))]
        end_price = price_df["close"].iloc[-1]
        price_change_pct = round((end_price - start_price) / start_price * 100, 2)
    else:
        price_change_pct = 0.0

    trend, trend_strength = _detect_trend(short_pcts, price_change_pct)
    alert_reasons = _generate_alerts(symbol, recent_short_pct, avg_short_pct, trend, trend_strength, price_change_pct)

    return DarkPoolResult(
        symbol=symbol,
        entries=entries,
        avg_short_pct=avg_short_pct,
        recent_short_pct=recent_short_pct,
        trend=trend,
        trend_strength=trend_strength,
        price_change_pct=price_change_pct,
        alert_reasons=alert_reasons,
    )


def _detect_trend(short_pcts: list[float], price_change_pct: float) -> tuple[str, float]:
    """Detect accumulation or distribution pattern.

    Accumulation: rising short volume % + flat/rising price
    Distribution: rising short volume % + falling price
    """
    if len(short_pcts) < 10:
        return "neutral", 0.0

    long_avg = np.mean(short_pcts)
    long_std = np.std(short_pcts) if np.std(short_pcts) > 0 else 1.0
    recent_avg = np.mean(short_pcts[-5:])

    # Z-score of recent short % vs long-term
    z_score = (recent_avg - long_avg) / long_std

    # Short % trend (slope of last 10 days)
    x = np.arange(min(10, len(short_pcts)))
    y = np.array(short_pcts[-10:])
    if len(x) >= 3:
        slope = np.polyfit(x, y[-len(x):], 1)[0]
    else:
        slope = 0

    # Combine signals
    strength = min(abs(z_score) / 2.0, 1.0)

    if z_score > 1.0 and price_change_pct >= -2.0:
        return "accumulating", round(strength, 2)
    elif z_score > 1.0 and price_change_pct < -2.0:
        return "distributing", round(strength, 2)
    elif slope > 0.5 and price_change_pct >= 0:
        return "accumulating", round(min(slope / 2.0, 1.0), 2)
    elif slope > 0.5 and price_change_pct < 0:
        return "distributing", round(min(slope / 2.0, 1.0), 2)
    else:
        return "neutral", 0.0


def _generate_alerts(
    symbol: str,
    recent_pct: float,
    avg_pct: float,
    trend: str,
    strength: float,
    price_change: float,
) -> list[str]:
    """Generate alert reasons for unusual dark pool activity."""
    alerts = []

    if trend == "accumulating" and strength >= 0.5:
        alerts.append(
            f"{symbol}: Short volume rising ({recent_pct:.1f}% vs {avg_pct:.1f}% avg) "
            f"while price {'up' if price_change >= 0 else 'flat'} {price_change:+.1f}% -- possible accumulation"
        )

    if trend == "distributing" and strength >= 0.5:
        alerts.append(
            f"{symbol}: Short volume rising ({recent_pct:.1f}% vs {avg_pct:.1f}% avg) "
            f"with price down {price_change:.1f}% -- possible distribution"
        )

    if recent_pct > 60:
        alerts.append(f"{symbol}: Unusually high short volume ({recent_pct:.1f}%)")

    if recent_pct < 30 and avg_pct > 40:
        alerts.append(f"{symbol}: Short volume dropped sharply ({recent_pct:.1f}% vs {avg_pct:.1f}% avg)")

    return alerts


def screen_universe(symbols: list[str], days: int = 20, top_n: int = 20) -> list[DarkPoolResult]:
    """Screen multiple symbols for dark pool activity.

    Returns results sorted by trend strength (strongest signals first).
    """
    # Filter out crypto symbols (no FINRA data)
    stock_symbols = [s for s in symbols if "/" not in s]

    batch_data = get_short_volume_batch(stock_symbols, days=days)
    results = []

    for symbol in stock_symbols:
        entries_raw = batch_data.get(symbol)
        if not entries_raw or len(entries_raw) < 5:
            continue

        try:
            price_df = alpaca_client.get_bars(symbol, days=days + 30)
            if price_df is None or price_df.empty:
                continue

            entries = [
                DarkPoolEntry(
                    symbol=symbol,
                    date=datetime.fromisoformat(e["date"]),
                    short_volume=e["short_volume"],
                    short_exempt_volume=e["short_exempt_volume"],
                    total_volume=e["total_volume"],
                    short_pct=e["short_pct"],
                )
                for e in entries_raw
            ]

            short_pcts = [e.short_pct for e in entries]
            avg_short_pct = round(np.mean(short_pcts), 2)
            recent_short_pct = round(np.mean(short_pcts[-5:]), 2)

            if len(price_df) >= 2:
                start_price = price_df["close"].iloc[-min(len(entries), len(price_df))]
                end_price = price_df["close"].iloc[-1]
                price_change_pct = round((end_price - start_price) / start_price * 100, 2)
            else:
                price_change_pct = 0.0

            trend, trend_strength = _detect_trend(short_pcts, price_change_pct)
            alert_reasons = _generate_alerts(symbol, recent_short_pct, avg_short_pct, trend, trend_strength, price_change_pct)

            results.append(DarkPoolResult(
                symbol=symbol,
                entries=entries,
                avg_short_pct=avg_short_pct,
                recent_short_pct=recent_short_pct,
                trend=trend,
                trend_strength=trend_strength,
                price_change_pct=price_change_pct,
                alert_reasons=alert_reasons,
            ))
        except Exception as e:
            logger.debug("Dark pool analysis failed for %s: %s", symbol, e)
            continue

    # Sort by trend strength, prioritize accumulating/distributing over neutral
    results.sort(key=lambda r: (r.trend != "neutral", r.trend_strength), reverse=True)
    return results[:top_n]
