"""Unit tests for analyzer.analyze_symbol (with mocked bar fetches)."""

import numpy as np
import pandas as pd
import pytest

from src.scanner import analyzer


def _make_ohlcv(n: int, trend: float, seed: int = 7, start: float = 50.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = start
    rows = []
    for _ in range(n):
        close = close * (1 + trend + rng.normal(0, 0.01))
        o = close * (1 + rng.normal(0, 0.003))
        h = max(o, close) * (1 + abs(rng.normal(0, 0.003)))
        lo = min(o, close) * (1 - abs(rng.normal(0, 0.003)))
        vol = int(rng.integers(1_000_000, 3_000_000))
        rows.append({"open": o, "high": h, "low": lo, "close": close, "volume": vol})
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2023-01-01", periods=n, freq="B")
    return df


@pytest.fixture
def patch_bars(monkeypatch):
    """Patch client.get_bars so analyze_symbol doesn't touch the network."""
    def _factory(sym_df: pd.DataFrame, spy_df: pd.DataFrame):
        def fake(symbol, days=260):  # noqa: ARG001
            return spy_df if symbol.upper() == "SPY" else sym_df
        monkeypatch.setattr(analyzer.client, "get_bars", fake)
    return _factory


class TestGradeAndVerdict:
    def test_grade_boundaries(self):
        assert analyzer._grade(90) == "A"
        assert analyzer._grade(70) == "B"
        assert analyzer._grade(55) == "C"
        assert analyzer._grade(40) == "D"
        assert analyzer._grade(10) == "F"

    def test_verdict_strong_buy(self):
        assert analyzer._verdict(80, "bullish") == "strong_buy"

    def test_verdict_avoid(self):
        assert analyzer._verdict(20, "bearish") == "avoid"

    def test_verdict_hold_middle(self):
        assert analyzer._verdict(50, "neutral") == "hold"


class TestTrendLabel:
    def test_bullish_stack(self):
        assert analyzer._trend_label(110, 105, 100) == "bullish"

    def test_bearish_stack(self):
        assert analyzer._trend_label(90, 95, 100) == "bearish"

    def test_turning_bullish(self):
        assert analyzer._trend_label(105, 100, 102) == "turning_bullish"


class TestAnalyzeSymbol:
    def test_uptrend_produces_high_score(self, patch_bars):
        strong = _make_ohlcv(260, trend=0.003, start=50)
        spy = _make_ohlcv(260, trend=0.001, start=400)
        patch_bars(strong, spy)
        result = analyzer.analyze_symbol("TEST")
        assert "error" not in result
        assert 0 <= result["composite_score"] <= 100
        assert result["trend"] in {"bullish", "turning_bullish"}
        assert result["verdict"] in {"buy", "strong_buy"}

    def test_downtrend_produces_low_score(self, patch_bars):
        weak = _make_ohlcv(260, trend=-0.003, start=50)
        spy = _make_ohlcv(260, trend=0.001, start=400)
        patch_bars(weak, spy)
        result = analyzer.analyze_symbol("TEST")
        assert "error" not in result
        assert result["trend"] in {"bearish", "turning_bearish"}
        assert result["verdict"] in {"hold", "avoid"}

    def test_insufficient_history_returns_error(self, monkeypatch):
        monkeypatch.setattr(
            analyzer.client,
            "get_bars",
            lambda *a, **kw: _make_ohlcv(30, trend=0.001),
        )
        result = analyzer.analyze_symbol("TEST")
        assert "error" in result
