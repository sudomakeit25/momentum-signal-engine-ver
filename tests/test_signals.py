"""Unit tests for signal generation, patterns, and risk management."""

import numpy as np
import pandas as pd
import pytest

from src.data.models import SignalAction, SetupType
from src.risk.position_sizer import calculate_position_size
from src.risk.rr_calculator import calculate_rr, find_target_for_rr, rate_setup
from src.signals.generator import generate_signals
from src.signals.patterns import (
    detect_patterns,
    is_earnings_gap_up,
    is_flag_pattern,
    is_flat_base,
    is_tight_consolidation,
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


class TestSignalGenerator:
    def test_generate_signals_returns_list(self):
        df = _make_ohlcv(n=200)
        signals = generate_signals(df, "TEST")
        assert isinstance(signals, list)

    def test_signals_have_required_fields(self):
        df = _make_ohlcv(n=200, trend=0.005)
        signals = generate_signals(df, "TEST")
        for s in signals:
            assert s.symbol == "TEST"
            assert s.action in (SignalAction.BUY, SignalAction.SELL)
            assert isinstance(s.entry, float)
            assert isinstance(s.rr_ratio, float)
            assert 0 <= s.confidence <= 1

    def test_buy_signal_stop_below_entry(self):
        df = _make_ohlcv(n=200, trend=0.005)
        signals = generate_signals(df, "TEST")
        buy_signals = [s for s in signals if s.action == SignalAction.BUY]
        for s in buy_signals:
            assert s.stop_loss < s.entry
            assert s.target > s.entry

    def test_insufficient_data_returns_empty(self):
        df = _make_ohlcv(n=10)
        assert generate_signals(df, "TEST") == []


class TestPatterns:
    def test_detect_patterns_returns_list(self):
        df = _make_ohlcv(n=200)
        patterns = detect_patterns(df)
        assert isinstance(patterns, list)
        for p in patterns:
            assert isinstance(p, SetupType)

    def test_tight_consolidation(self):
        # Create very tight price action
        df = _make_ohlcv(n=100, trend=0.0)
        # Force last 10 bars to be very tight
        base_price = df["close"].iloc[-11]
        for i in range(-10, 0):
            df.iloc[i, df.columns.get_loc("open")] = base_price
            df.iloc[i, df.columns.get_loc("high")] = base_price * 1.001
            df.iloc[i, df.columns.get_loc("low")] = base_price * 0.999
            df.iloc[i, df.columns.get_loc("close")] = base_price
        assert is_tight_consolidation(df)

    def test_flat_base(self):
        df = _make_ohlcv(n=100)
        # Force flat base: last 20 bars all near the same price
        base_price = df["high"].max()
        for i in range(-20, 0):
            df.iloc[i, df.columns.get_loc("open")] = base_price * 0.98
            df.iloc[i, df.columns.get_loc("high")] = base_price
            df.iloc[i, df.columns.get_loc("low")] = base_price * 0.95
            df.iloc[i, df.columns.get_loc("close")] = base_price * 0.99
        assert is_flat_base(df)

    def test_gap_up(self):
        df = _make_ohlcv(n=100)
        prev_close = df["close"].iloc[-2]
        # Force a big gap up with high volume
        df.iloc[-1, df.columns.get_loc("open")] = prev_close * 1.05
        df.iloc[-1, df.columns.get_loc("close")] = prev_close * 1.06
        df.iloc[-1, df.columns.get_loc("high")] = prev_close * 1.07
        df.iloc[-1, df.columns.get_loc("volume")] = 10_000_000
        assert is_earnings_gap_up(df)

    def test_insufficient_data(self):
        df = _make_ohlcv(n=10)
        assert detect_patterns(df) == []


class TestRiskReward:
    def test_calculate_rr(self):
        assert calculate_rr(50.0, 47.0, 56.0) == 2.0

    def test_calculate_rr_zero_risk(self):
        assert calculate_rr(50.0, 50.0, 56.0) == 0.0

    def test_rate_setup_poor(self):
        assert rate_setup(1.0) == "poor"

    def test_rate_setup_decent(self):
        assert rate_setup(1.7) == "decent"

    def test_rate_setup_good(self):
        assert rate_setup(2.5) == "good"

    def test_rate_setup_excellent(self):
        assert rate_setup(4.0) == "excellent"

    def test_find_target(self):
        target = find_target_for_rr(50.0, 47.0, 3.0)
        assert target == 59.0  # 50 + 3 * (50 - 47)


class TestPositionSizer:
    def test_basic_position_size(self):
        result = calculate_position_size(
            account_size=100_000, risk_pct=2.0, entry=50.0, stop_loss=47.0
        )
        assert result.shares == 666  # $2000 risk / $3 per share
        assert result.dollar_risk == 2000.0
        assert result.rr_ratio == 2.0  # Default 2:1 target

    def test_with_custom_target(self):
        result = calculate_position_size(
            account_size=100_000, risk_pct=1.0, entry=50.0, stop_loss=48.0, target=56.0
        )
        assert result.shares == 500  # $1000 risk / $2 per share
        assert result.rr_ratio == 3.0

    def test_zero_risk(self):
        result = calculate_position_size(
            account_size=100_000, risk_pct=2.0, entry=50.0, stop_loss=50.0
        )
        assert result.shares == 0

    def test_position_value(self):
        result = calculate_position_size(
            account_size=50_000, risk_pct=2.0, entry=100.0, stop_loss=95.0
        )
        expected_shares = int(1000 / 5)  # 200 shares
        assert result.shares == expected_shares
        assert result.position_value == expected_shares * 100.0
