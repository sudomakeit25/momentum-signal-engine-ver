"""Unit tests for technical indicators."""

import numpy as np
import pandas as pd
import pytest

from src.signals.indicators import (
    add_all_indicators,
    atr,
    atr_trailing_stop,
    ema,
    ema_crossover,
    ema_crossunder,
    is_ema_stacked,
    macd,
    relative_strength_vs_spy,
    rsi,
    rsi_divergence,
    rsi_pullback_in_uptrend,
    sma,
    volume_climax,
    volume_sma,
    volume_surge,
    vwap,
)


def _make_ohlcv(n: int = 100, trend: float = 0.001, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    close = 100.0
    rows = []
    for i in range(n):
        close = close * (1 + trend + rng.normal(0, 0.02))
        o = close * (1 + rng.normal(0, 0.005))
        h = max(o, close) * (1 + abs(rng.normal(0, 0.005)))
        lo = min(o, close) * (1 - abs(rng.normal(0, 0.005)))
        vol = int(rng.integers(500_000, 2_000_000))
        rows.append({"open": o, "high": h, "low": lo, "close": close, "volume": vol})
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2024-01-01", periods=n, freq="B")
    return df


class TestEMA:
    def test_ema_length(self):
        df = _make_ohlcv()
        result = ema(df["close"], 9)
        assert len(result) == len(df)

    def test_ema_smoothing(self):
        df = _make_ohlcv()
        ema9 = ema(df["close"], 9)
        ema50 = ema(df["close"], 50)
        # Short EMA should react faster — last values should differ
        assert ema9.iloc[-1] != ema50.iloc[-1]

    def test_sma_length(self):
        df = _make_ohlcv()
        result = sma(df["close"], 20)
        assert len(result) == len(df)
        # First 19 values should be NaN
        assert result.iloc[:19].isna().all()
        assert pd.notna(result.iloc[19])


class TestRSI:
    def test_rsi_range(self):
        df = _make_ohlcv()
        result = rsi(df["close"])
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_uptrend(self):
        # Strong uptrend should have RSI > 50
        df = _make_ohlcv(trend=0.005)
        result = rsi(df["close"])
        assert result.iloc[-1] > 50


class TestMACD:
    def test_macd_components(self):
        df = _make_ohlcv()
        line, signal, hist = macd(df["close"])
        assert len(line) == len(df)
        assert len(signal) == len(df)
        assert len(hist) == len(df)


class TestATR:
    def test_atr_positive(self):
        df = _make_ohlcv()
        result = atr(df)
        # Skip warmup period — ATR needs at least 14 bars
        valid = result.iloc[14:].dropna()
        assert (valid > 0).all()

    def test_atr_trailing_stop_below_price(self):
        df = _make_ohlcv(trend=0.005)
        stop = atr_trailing_stop(df)
        # Trailing stop should be below the current price in an uptrend
        valid_stop = stop.dropna()
        assert valid_stop.iloc[-1] < df["close"].iloc[-1]


class TestVWAP:
    def test_vwap_reasonable(self):
        df = _make_ohlcv()
        result = vwap(df)
        # VWAP should be in the range of prices
        assert result.iloc[-1] > df["low"].min() * 0.5
        assert result.iloc[-1] < df["high"].max() * 1.5


class TestRelativeStrength:
    def test_rs_outperformer(self):
        stock = pd.Series(np.linspace(100, 150, 100))  # +50%
        spy = pd.Series(np.linspace(100, 110, 100))  # +10%
        rs = relative_strength_vs_spy(stock, spy, 63)
        assert rs.iloc[-1] > 1.0

    def test_rs_underperformer(self):
        stock = pd.Series(np.linspace(100, 95, 100))  # -5%
        spy = pd.Series(np.linspace(100, 110, 100))  # +10%
        rs = relative_strength_vs_spy(stock, spy, 63)
        assert rs.iloc[-1] < 1.0


class TestVolume:
    def test_volume_sma(self):
        df = _make_ohlcv()
        result = volume_sma(df["volume"], 20)
        valid = result.dropna()
        assert len(valid) == len(df) - 19

    def test_volume_surge_detection(self):
        df = _make_ohlcv()
        # Spike the last bar's volume
        df.iloc[-1, df.columns.get_loc("volume")] = 10_000_000
        surges = volume_surge(df, multiplier=2.0)
        assert surges.iloc[-1]


class TestCrossovers:
    def test_ema_crossover_detection(self):
        df = _make_ohlcv(n=200, trend=0.003)
        crossovers = ema_crossover(df["close"], 9, 21)
        # Should detect at least one crossover in trending data
        assert crossovers.any()

    def test_ema_crossunder_detection(self):
        df = _make_ohlcv(n=200, trend=-0.003)
        crossunders = ema_crossunder(df["close"], 9, 21)
        assert crossunders.any()


class TestEMAStacked:
    def test_stacked_in_uptrend(self):
        df = _make_ohlcv(n=200, trend=0.005)
        stacked = is_ema_stacked(df)
        # In a strong uptrend, EMAs should be stacked at some point
        assert stacked.any()


class TestAddAllIndicators:
    def test_adds_expected_columns(self):
        df = _make_ohlcv()
        result = add_all_indicators(df)
        expected = [
            "ema9", "ema21", "ema50", "ema200",
            "rsi", "macd_line", "macd_signal", "macd_hist",
            "atr", "volume_sma20", "ema_stacked", "volume_surge",
        ]
        for col in expected:
            assert col in result.columns, f"Missing column: {col}"
