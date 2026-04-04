"""Core momentum scanner — ranks stocks by momentum criteria."""

import pandas as pd

from src.signals.indicators import (
    ema,
    is_ema_stacked,
    relative_strength_vs_spy,
    volume_sma,
    volume_surge,
)


def rs_ranking(
    stock_close: pd.Series,
    spy_close: pd.Series,
) -> dict[str, float]:
    """Compute relative strength vs SPY over 1m, 3m, 6m periods."""
    periods = {"1m": 21, "3m": 63, "6m": 126}
    scores: dict[str, float] = {}
    for label, period in periods.items():
        if len(stock_close) < period or len(spy_close) < period:
            scores[label] = 0.0
            continue
        rs = relative_strength_vs_spy(stock_close, spy_close, period)
        scores[label] = float(rs.iloc[-1]) if pd.notna(rs.iloc[-1]) else 0.0
    return scores


def is_volume_surging(df: pd.DataFrame, multiplier: float = 2.0) -> bool:
    """Check if the latest bar has a volume surge."""
    surges = volume_surge(df, multiplier)
    return bool(surges.iloc[-1]) if not surges.empty else False


def is_near_52w_high(df: pd.DataFrame, threshold: float = 0.15) -> bool:
    """Check if price is within `threshold` (15%) of 52-week high."""
    if len(df) < 5:
        return False
    # Use up to 252 trading days for 52-week
    lookback = min(len(df), 252)
    high_52w = df["high"].tail(lookback).max()
    last_close = df["close"].iloc[-1]
    return last_close >= high_52w * (1 - threshold)


def is_ema_aligned(df: pd.DataFrame) -> bool:
    """Check if EMAs are stacked bullishly on the latest bar."""
    stacked = is_ema_stacked(df)
    return bool(stacked.iloc[-1]) if not stacked.empty else False


def detect_breakout(df: pd.DataFrame, lookback: int = 20) -> bool:
    """Detect if the latest bar is a breakout above recent resistance on volume.

    Resistance = highest high in the lookback period (excluding latest bar).
    Breakout = close above resistance AND volume surge.
    """
    if len(df) < lookback + 1:
        return False
    resistance = df["high"].iloc[-(lookback + 1) : -1].max()
    last_close = df["close"].iloc[-1]
    surging = is_volume_surging(df, multiplier=1.5)
    return last_close > resistance and surging


def compute_momentum_score(
    df: pd.DataFrame,
    spy_df: pd.DataFrame,
) -> float:
    """Compute a composite momentum score (0-100) for a stock.

    Criteria (each 0-20 points):
    1. RS vs SPY (3-month)
    2. Volume surge
    3. Near 52-week high
    4. EMA alignment
    5. Breakout detection
    """
    score = 0.0

    # 1. Relative strength (0-20)
    if len(df) >= 63 and len(spy_df) >= 63:
        rs = rs_ranking(df["close"], spy_df["close"])
        rs_3m = rs.get("3m", 1.0)
        # RS > 1.1 = full points, scale linearly
        score += min(20.0, max(0.0, (rs_3m - 0.9) * 100))

    # 2. Volume surge (0-20)
    if is_volume_surging(df, multiplier=1.5):
        avg_vol = volume_sma(df["volume"], 20).iloc[-1]
        if avg_vol > 0:
            ratio = df["volume"].iloc[-1] / avg_vol
            score += min(20.0, ratio * 5)

    # 3. Near 52-week high (0-20)
    if is_near_52w_high(df, 0.05):
        score += 20.0
    elif is_near_52w_high(df, 0.10):
        score += 12.0
    elif is_near_52w_high(df, 0.15):
        score += 6.0

    # 4. EMA alignment (0-20)
    if is_ema_aligned(df):
        score += 20.0
    else:
        # Partial credit: price above EMA50
        ema50 = ema(df["close"], 50)
        if not ema50.empty and df["close"].iloc[-1] > ema50.iloc[-1]:
            score += 8.0

    # 5. Breakout (0-20)
    if detect_breakout(df):
        score += 20.0

    return min(100.0, score)
