"""Unit tests for instrument_indicators (DPO, Stochastic, Williams%R, ROC, Mood)."""

import numpy as np
import pandas as pd
import pytest

from src.scanner import instrument_indicators as ii


def _make_bars(n: int, trend: float = 0.001, seed: int = 1, start: float = 50.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = start
    rows = []
    for _ in range(n):
        close *= 1 + trend + rng.normal(0, 0.01)
        rows.append({
            "open": close, "high": close * 1.01, "low": close * 0.99,
            "close": close, "volume": 1_000_000,
        })
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2024-01-01", periods=n, freq="B")
    return df


class TestDPO:
    def test_shape_matches_input(self):
        df = _make_bars(100)
        out = ii._dpo(df["close"], 20)
        assert len(out) == len(df)

    def test_flat_series_is_zero(self):
        close = pd.Series([100.0] * 50)
        out = ii._dpo(close, 20).dropna()
        assert len(out) > 0
        # Flat series → SMA == close_shifted → DPO near 0
        assert all(abs(v) < 0.01 for v in out)


class TestStochastic:
    def test_bounds(self):
        df = _make_bars(60)
        k, d = ii._stochastic(df["high"], df["low"], df["close"], 14)
        dropped = k.dropna()
        assert (dropped >= 0).all() and (dropped <= 100).all()


class TestWilliamsR:
    def test_bounds(self):
        df = _make_bars(60)
        wr = ii._williams_r(df["high"], df["low"], df["close"], 14).dropna()
        assert (wr >= -100).all() and (wr <= 0).all()


class TestROC:
    def test_basic(self):
        close = pd.Series([100.0, 102.0, 104.04])
        roc = ii._roc(close, 1)
        assert roc.iloc[1] == pytest.approx(2.0, abs=0.01)
        assert roc.iloc[2] == pytest.approx(2.0, abs=0.01)


class TestGetIndicatorSeries:
    def test_full_bundle(self, monkeypatch):
        monkeypatch.setattr(ii.client, "get_bars", lambda sym, days=260: _make_bars(260, trend=0.002))
        r = ii.get_indicator_series("TEST")
        assert "error" not in r
        assert r["mood"]["score"] is not None
        for key in ["rsi", "macd_hist", "dpo_20", "stoch_k", "williams_r", "roc_10"]:
            assert key in r["snapshot"]
        assert len(r["series"]) > 0

    def test_insufficient_history(self, monkeypatch):
        monkeypatch.setattr(ii.client, "get_bars", lambda sym, days=260: _make_bars(20))
        r = ii.get_indicator_series("TEST")
        assert "error" in r

    def test_fetch_exception(self, monkeypatch):
        def boom(sym, days=260):
            raise RuntimeError("bar fetch failed")
        monkeypatch.setattr(ii.client, "get_bars", boom)
        r = ii.get_indicator_series("TEST")
        assert "error" in r

    def test_uptrend_produces_bullish_mood(self, monkeypatch):
        monkeypatch.setattr(ii.client, "get_bars", lambda sym, days=260: _make_bars(260, trend=0.005, seed=7))
        r = ii.get_indicator_series("TEST")
        assert r["mood"]["score"] >= 55
        assert r["mood"]["label"] in {"bullish", "greed", "extreme_greed"}
