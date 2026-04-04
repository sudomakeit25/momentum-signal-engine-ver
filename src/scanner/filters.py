"""Reusable filter functions for stock screening."""

import pandas as pd


def price_filter(
    df: pd.DataFrame,
    min_price: float = 5.0,
    max_price: float = 500.0,
) -> bool:
    """Check if the latest close is within the price range."""
    if df.empty:
        return False
    last_close = df["close"].iloc[-1]
    return min_price <= last_close <= max_price


def volume_filter(df: pd.DataFrame, min_avg_volume: int = 500_000) -> bool:
    """Check if 20-day average volume exceeds threshold."""
    if len(df) < 20:
        return False
    avg_vol = df["volume"].tail(20).mean()
    return avg_vol >= min_avg_volume


def market_cap_filter(
    price: float,
    shares_outstanding: float | None,
    min_cap: float = 0,
    max_cap: float = float("inf"),
) -> bool:
    """Check if estimated market cap is within range."""
    if shares_outstanding is None:
        return True  # Skip filter if data unavailable
    cap = price * shares_outstanding
    return min_cap <= cap <= max_cap


def sector_filter(sector: str | None, allowed_sectors: list[str] | None) -> bool:
    """Check if the stock's sector is in the allowed list."""
    if allowed_sectors is None:
        return True
    if sector is None:
        return False
    return sector in allowed_sectors


def apply_filters(
    df: pd.DataFrame,
    min_price: float = 5.0,
    max_price: float = 500.0,
    min_avg_volume: int = 500_000,
) -> bool:
    """Apply all basic filters. Returns True if the stock passes."""
    return price_filter(df, min_price, max_price) and volume_filter(
        df, min_avg_volume
    )
