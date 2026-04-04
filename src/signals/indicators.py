"""Technical indicators built on top of the `ta` library and pandas."""

import numpy as np
import pandas as pd
import ta


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return ta.trend.ema_indicator(series, window=period)


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return ta.trend.sma_indicator(series, window=period)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    return ta.momentum.rsi(series, window=period)


def macd(series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram."""
    indicator = ta.trend.MACD(series)
    return indicator.macd(), indicator.macd_signal(), indicator.macd_diff()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range. Expects columns: high, low, close."""
    return ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=period
    )


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume Weighted Average Price.

    Expects columns: high, low, close, volume.
    Calculates cumulative VWAP from the start of the DataFrame
    (typically reset each trading day for intraday use).
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cumulative_tp_vol = (typical_price * df["volume"]).cumsum()
    cumulative_vol = df["volume"].cumsum()
    return cumulative_tp_vol / cumulative_vol


def relative_strength_vs_spy(
    stock_close: pd.Series,
    spy_close: pd.Series,
    period: int = 63,  # ~3 months
) -> pd.Series:
    """Relative strength of a stock vs SPY over a rolling period.

    Returns a ratio: >1 means the stock outperformed SPY.
    """
    stock_ret = stock_close.pct_change(period)
    spy_ret = spy_close.pct_change(period)
    # Avoid division by zero
    rs = (1 + stock_ret) / (1 + spy_ret)
    return rs


def volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    """Simple moving average of volume."""
    return volume.rolling(window=period).mean()


def is_ema_stacked(df: pd.DataFrame) -> pd.Series:
    """Check if EMAs are stacked bullishly: price > EMA9 > EMA21 > EMA50."""
    ema9 = ema(df["close"], 9)
    ema21 = ema(df["close"], 21)
    ema50 = ema(df["close"], 50)
    return (df["close"] > ema9) & (ema9 > ema21) & (ema21 > ema50)


def ema_crossover(series: pd.Series, fast: int = 9, slow: int = 21) -> pd.Series:
    """Detect bullish EMA crossover. Returns True on crossover bars."""
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    crossed_above = (fast_ema > slow_ema) & (fast_ema.shift(1) <= slow_ema.shift(1))
    return crossed_above


def ema_crossunder(series: pd.Series, fast: int = 9, slow: int = 21) -> pd.Series:
    """Detect bearish EMA crossunder. Returns True on crossunder bars."""
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    crossed_below = (fast_ema < slow_ema) & (fast_ema.shift(1) >= slow_ema.shift(1))
    return crossed_below


def rsi_pullback_in_uptrend(df: pd.DataFrame) -> pd.Series:
    """RSI between 40-50 while EMAs are stacked bullishly."""
    rsi_val = rsi(df["close"])
    stacked = is_ema_stacked(df)
    return stacked & (rsi_val >= 40) & (rsi_val <= 50)


def volume_surge(df: pd.DataFrame, multiplier: float = 2.0) -> pd.Series:
    """Detect volume surges: current volume > multiplier * 20-day avg."""
    avg_vol = volume_sma(df["volume"], 20)
    return df["volume"] > (multiplier * avg_vol)


def atr_trailing_stop(df: pd.DataFrame, multiplier: float = 2.0) -> pd.Series:
    """Calculate ATR trailing stop level (2x ATR below the rolling high)."""
    atr_val = atr(df)
    rolling_high = df["high"].rolling(window=20).max()
    return rolling_high - (multiplier * atr_val)


def rsi_divergence(df: pd.DataFrame, lookback: int = 14) -> pd.Series:
    """Detect bearish RSI divergence: price makes new high, RSI doesn't.

    Returns True on bars where divergence is detected.
    """
    rsi_val = rsi(df["close"])
    price_new_high = df["close"] == df["close"].rolling(lookback).max()
    rsi_new_high = rsi_val == rsi_val.rolling(lookback).max()
    return price_new_high & ~rsi_new_high


def volume_climax(df: pd.DataFrame, multiplier: float = 3.0) -> pd.Series:
    """Detect volume climax: huge volume spike on a down candle."""
    avg_vol = volume_sma(df["volume"], 20)
    is_down = df["close"] < df["open"]
    is_spike = df["volume"] > (multiplier * avg_vol)
    return is_down & is_spike


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all standard indicators to a DataFrame as new columns."""
    df = df.copy()
    df["ema9"] = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["rsi"] = rsi(df["close"])
    df["macd_line"], df["macd_signal"], df["macd_hist"] = macd(df["close"])
    df["atr"] = atr(df)
    df["volume_sma20"] = volume_sma(df["volume"])
    df["ema_stacked"] = is_ema_stacked(df)
    df["volume_surge"] = volume_surge(df)
    return df
