"""Chart pattern detection — flags, bases, consolidation, gaps."""

import numpy as np
import pandas as pd

from src.data.models import SetupType
from src.signals.indicators import atr, ema, is_ema_stacked


def detect_patterns(df: pd.DataFrame) -> list[SetupType]:
    """Detect all chart patterns present in the data.

    Args:
        df: DataFrame with OHLCV data (at least 50 bars).

    Returns:
        List of detected SetupType values.
    """
    if len(df) < 50:
        return []

    patterns: list[SetupType] = []

    if is_tight_consolidation(df):
        patterns.append(SetupType.TIGHT_CONSOLIDATION)
    if is_flag_pattern(df):
        patterns.append(SetupType.FLAG)
    if is_flat_base(df):
        patterns.append(SetupType.FLAT_BASE)
    if is_earnings_gap_up(df):
        patterns.append(SetupType.GAP_UP)

    return patterns


def is_tight_consolidation(df: pd.DataFrame, lookback: int = 10) -> bool:
    """Detect tight consolidation (low volatility squeeze).

    Criteria: the range (high - low) of the last `lookback` bars
    is less than 1x the 14-day ATR.
    """
    if len(df) < lookback + 14:
        return False
    atr_val = atr(df).iloc[-1]
    if pd.isna(atr_val) or atr_val <= 0:
        return False
    recent = df.tail(lookback)
    price_range = recent["high"].max() - recent["low"].min()
    return price_range < atr_val * 1.5


def is_flag_pattern(
    df: pd.DataFrame,
    rally_lookback: int = 20,
    pullback_lookback: int = 10,
) -> bool:
    """Detect bull flag: strong rally followed by tight pullback in an uptrend.

    Criteria:
    1. Price rallied >10% in the prior `rally_lookback` bars.
    2. Recent `pullback_lookback` bars pulled back less than 50% of the rally.
    3. EMAs are stacked bullishly.
    """
    needed = rally_lookback + pullback_lookback
    if len(df) < needed:
        return False

    # Rally phase
    rally_start = df["close"].iloc[-(needed)]
    rally_end = df["close"].iloc[-(pullback_lookback)]
    rally_pct = (rally_end - rally_start) / rally_start if rally_start > 0 else 0

    if rally_pct < 0.10:
        return False

    # Pullback phase
    pullback_low = df["low"].tail(pullback_lookback).min()
    pullback_depth = (rally_end - pullback_low) / (rally_end - rally_start)

    if pullback_depth > 0.50:
        return False

    # Trend confirmation
    stacked = is_ema_stacked(df)
    return bool(stacked.iloc[-1]) if not stacked.empty else False


def is_flat_base(df: pd.DataFrame, lookback: int = 20) -> bool:
    """Detect flat base breakout: price consolidates near highs.

    Criteria:
    1. Price is within 5% of the `lookback`-period high.
    2. The range of the consolidation is < 10% of the price.
    """
    if len(df) < lookback:
        return False
    recent = df.tail(lookback)
    period_high = recent["high"].max()
    period_low = recent["low"].min()
    last_close = df["close"].iloc[-1]

    near_high = last_close >= period_high * 0.95
    tight_range = (period_high - period_low) / period_high < 0.10

    return near_high and tight_range


def is_earnings_gap_up(df: pd.DataFrame) -> bool:
    """Detect earnings-style gap up: significant gap with high volume.

    Criteria:
    1. Open is >3% above prior close.
    2. Volume is >2x the 20-day average.
    """
    if len(df) < 21:
        return False
    last = df.iloc[-1]
    prev_close = df["close"].iloc[-2]
    gap_pct = (last["open"] - prev_close) / prev_close if prev_close > 0 else 0

    avg_vol = df["volume"].tail(20).mean()
    vol_ratio = last["volume"] / avg_vol if avg_vol > 0 else 0

    return gap_pct > 0.03 and vol_ratio > 2.0
