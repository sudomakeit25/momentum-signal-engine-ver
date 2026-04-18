"""Unit tests for seasonality."""

import numpy as np
import pandas as pd

from src.scanner import seasonality as sn


def _make_bars(n: int, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0
    rows = []
    for _ in range(n):
        close *= 1 + rng.normal(0, 0.01)
        rows.append({"open": close, "high": close * 1.01, "low": close * 0.99,
                     "close": close, "volume": 1_000_000})
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2015-01-01", periods=n, freq="B")
    return df


def test_returns_twelve_months(monkeypatch):
    monkeypatch.setattr(sn.client, "get_bars", lambda sym, days=3650: _make_bars(2500))
    r = sn.analyze_seasonality("TEST")
    assert len(r["months"]) == 12
    assert [m["label"] for m in r["months"]][:3] == ["Jan", "Feb", "Mar"]


def test_short_history_returns_error(monkeypatch):
    monkeypatch.setattr(sn.client, "get_bars", lambda sym, days=3650: _make_bars(10))
    assert "error" in sn.analyze_seasonality("TEST")


def test_fetch_exception_returns_error(monkeypatch):
    def boom(sym, days=3650):
        raise RuntimeError("alpaca down")
    monkeypatch.setattr(sn.client, "get_bars", boom)
    r = sn.analyze_seasonality("TEST")
    assert "alpaca down" in r["error"]


def test_heatmap_rows_per_year(monkeypatch):
    monkeypatch.setattr(sn.client, "get_bars", lambda sym, days=3650: _make_bars(2500))
    r = sn.analyze_seasonality("TEST")
    assert r["years_covered"] == len(r["heatmap"])
    assert "year" in r["heatmap"][0]
