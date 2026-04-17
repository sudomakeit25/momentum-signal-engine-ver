"""Unit tests for preset_screener._passes strategy logic."""

import numpy as np
import pandas as pd

from src.scanner.preset_screener import STRATEGIES, _passes, list_strategies


def _make_ohlcv(
    n: int = 260,
    trend: float = 0.002,
    seed: int = 42,
    start_price: float = 50.0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = start_price
    rows = []
    for _ in range(n):
        close = close * (1 + trend + rng.normal(0, 0.015))
        o = close * (1 + rng.normal(0, 0.003))
        h = max(o, close) * (1 + abs(rng.normal(0, 0.003)))
        lo = min(o, close) * (1 - abs(rng.normal(0, 0.003)))
        vol = int(rng.integers(1_000_000, 3_000_000))
        rows.append({"open": o, "high": h, "low": lo, "close": close, "volume": vol})
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2023-01-01", periods=n, freq="B")
    return df


class TestPresetScreenerMetadata:
    def test_list_strategies_matches_dict(self):
        keys = {s["key"] for s in list_strategies()}
        assert keys == set(STRATEGIES.keys())

    def test_unknown_strategy_short_circuits(self):
        ok, note = _passes("does_not_exist", _make_ohlcv(), 80, 1.2, 2.0)
        assert not ok
        assert "unknown" in note


class TestPassesGuards:
    def test_insufficient_bars_rejected(self):
        short = _make_ohlcv(n=30)
        for strat in STRATEGIES.keys():
            ok, note = _passes(strat, short, 80, 1.2, 2.0)
            assert not ok, f"{strat} should reject short df"
            assert "insufficient" in note


class TestMomentumStrategy:
    def test_momentum_passes_strong_uptrend(self):
        df = _make_ohlcv(trend=0.003)
        ok, _ = _passes("momentum", df, score=75, rs=1.2, change_pct=1.5)
        assert ok

    def test_momentum_fails_low_score(self):
        df = _make_ohlcv(trend=0.003)
        ok, _ = _passes("momentum", df, score=40, rs=1.2, change_pct=1.5)
        assert not ok

    def test_momentum_fails_weak_rs(self):
        df = _make_ohlcv(trend=0.003)
        ok, _ = _passes("momentum", df, score=75, rs=0.8, change_pct=1.5)
        assert not ok


class TestTrendFollowStrategy:
    def test_trend_follow_passes_long_uptrend(self):
        df = _make_ohlcv(n=300, trend=0.003)
        ok, note = _passes("trend_follow", df, score=0, rs=0, change_pct=0)
        assert ok
        assert "ret_1y" in note

    def test_trend_follow_fails_downtrend(self):
        df = _make_ohlcv(n=300, trend=-0.003)
        ok, _ = _passes("trend_follow", df, score=0, rs=0, change_pct=0)
        assert not ok


class TestOversoldBounce:
    def test_oversold_requires_rsi_under_30(self):
        df = _make_ohlcv(n=260, trend=0.001)
        # non-oversold df should fail the RSI gate
        ok, _ = _passes("oversold_bounce", df, 0, 0, 0)
        assert not ok
