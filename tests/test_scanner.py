"""Unit tests for scanner filters and momentum scoring."""

import numpy as np
import pandas as pd
import pytest

from src.scanner.filters import (
    apply_filters,
    market_cap_filter,
    price_filter,
    sector_filter,
    volume_filter,
)
from src.scanner.momentum import (
    compute_momentum_score,
    detect_breakout,
    is_ema_aligned,
    is_near_52w_high,
    is_volume_surging,
    rs_ranking,
)


def _make_ohlcv(n: int = 100, trend: float = 0.001, seed: int = 42) -> pd.DataFrame:
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


class TestFilters:
    def test_price_filter_pass(self):
        df = _make_ohlcv()
        assert price_filter(df, 5, 500)

    def test_price_filter_fail_low(self):
        df = _make_ohlcv()
        assert not price_filter(df, 200, 500)  # Price starts ~100

    def test_price_filter_empty(self):
        df = pd.DataFrame(columns=["close"])
        assert not price_filter(df)

    def test_volume_filter_pass(self):
        df = _make_ohlcv()
        assert volume_filter(df, min_avg_volume=100_000)

    def test_volume_filter_fail(self):
        df = _make_ohlcv()
        assert not volume_filter(df, min_avg_volume=10_000_000)

    def test_volume_filter_insufficient_data(self):
        df = _make_ohlcv(n=5)
        assert not volume_filter(df)

    def test_market_cap_filter_pass(self):
        assert market_cap_filter(100, 1_000_000, min_cap=50_000_000)

    def test_market_cap_filter_fail(self):
        assert not market_cap_filter(100, 100_000, min_cap=50_000_000)

    def test_market_cap_filter_no_shares(self):
        # Should pass when shares_outstanding is None
        assert market_cap_filter(100, None, min_cap=50_000_000)

    def test_sector_filter_pass(self):
        assert sector_filter("Technology", ["Technology", "Healthcare"])

    def test_sector_filter_fail(self):
        assert not sector_filter("Energy", ["Technology", "Healthcare"])

    def test_sector_filter_no_filter(self):
        assert sector_filter("Anything", None)

    def test_apply_filters_pass(self):
        df = _make_ohlcv()
        assert apply_filters(df, min_price=5, max_price=500, min_avg_volume=100_000)


class TestMomentum:
    def test_rs_ranking_keys(self):
        stock = pd.Series(np.linspace(100, 150, 200))
        spy = pd.Series(np.linspace(100, 120, 200))
        rs = rs_ranking(stock, spy)
        assert "1m" in rs
        assert "3m" in rs
        assert "6m" in rs

    def test_volume_surging(self):
        df = _make_ohlcv()
        df.iloc[-1, df.columns.get_loc("volume")] = 10_000_000
        assert is_volume_surging(df)

    def test_volume_not_surging(self):
        df = _make_ohlcv()
        assert not is_volume_surging(df, multiplier=100)

    def test_near_52w_high_yes(self):
        # Uptrending stock should be near highs
        df = _make_ohlcv(n=252, trend=0.003)
        assert is_near_52w_high(df, 0.15)

    def test_near_52w_high_no(self):
        # Downtrending stock should NOT be near highs
        df = _make_ohlcv(n=252, trend=-0.005)
        assert not is_near_52w_high(df, 0.05)

    def test_ema_aligned_uptrend(self):
        df = _make_ohlcv(n=200, trend=0.005)
        # In a strong uptrend, EMAs should be stacked at some point
        from src.signals.indicators import is_ema_stacked

        stacked = is_ema_stacked(df)
        assert stacked.any()

    def test_detect_breakout_with_volume(self):
        df = _make_ohlcv(n=100)
        # Force a breakout: set last close above all previous highs with huge volume
        df.iloc[-1, df.columns.get_loc("close")] = df["high"].max() + 10
        df.iloc[-1, df.columns.get_loc("volume")] = 10_000_000
        assert detect_breakout(df)

    def test_momentum_score_range(self):
        df = _make_ohlcv(n=200, trend=0.003)
        spy_df = _make_ohlcv(n=200, trend=0.001, seed=99)
        score = compute_momentum_score(df, spy_df)
        assert 0 <= score <= 100
