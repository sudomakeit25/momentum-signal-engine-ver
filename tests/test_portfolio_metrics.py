"""Unit tests for portfolio_metrics.analyze_portfolio (mocked data)."""

import numpy as np
import pandas as pd
import pytest

from src.scanner import portfolio_metrics as pm


def _make_bars(n: int, trend: float, seed: int, start: float = 50.0) -> pd.DataFrame:
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


@pytest.fixture
def patch_sources(monkeypatch):
    def _factory(bars: dict[str, pd.DataFrame], sectors: dict[str, str]):
        monkeypatch.setattr(pm.client, "get_multi_bars", lambda syms, days=400: bars)
        monkeypatch.setattr(pm, "_sector_of", lambda sym: sectors.get(sym, "Unknown"))
    return _factory


class TestAnalyzePortfolio:
    def test_basic_weights_and_totals(self, patch_sources):
        bars = {
            "AAA": _make_bars(260, 0.002, 1, start=100),
            "BBB": _make_bars(260, 0.001, 2, start=50),
            "SPY": _make_bars(260, 0.0005, 99, start=400),
        }
        patch_sources(bars, {"AAA": "Tech", "BBB": "Health"})

        result = pm.analyze_portfolio([
            {"symbol": "AAA", "shares": 10},
            {"symbol": "BBB", "shares": 20},
        ])

        assert "error" not in result
        aaa_price = float(bars["AAA"]["close"].iloc[-1])
        bbb_price = float(bars["BBB"]["close"].iloc[-1])
        expected_total = aaa_price * 10 + bbb_price * 20
        assert result["total_value"] == pytest.approx(round(expected_total, 2), rel=1e-4)

        by_sym = {h["symbol"]: h for h in result["holdings"]}
        assert by_sym["AAA"]["sector"] == "Tech"
        assert by_sym["BBB"]["sector"] == "Health"
        # Weights sum to ~1.0
        assert sum(h["weight"] for h in result["holdings"]) == pytest.approx(1.0, abs=0.01)

    def test_correlation_matrix_shape(self, patch_sources):
        bars = {
            "AAA": _make_bars(120, 0.001, 3),
            "BBB": _make_bars(120, 0.001, 4),
            "CCC": _make_bars(120, 0.001, 5),
            "SPY": _make_bars(120, 0.0005, 99),
        }
        patch_sources(bars, {})
        result = pm.analyze_portfolio([
            {"symbol": s, "shares": 1} for s in ("AAA", "BBB", "CCC")
        ])
        corr = result["correlation"]
        assert corr["symbols"] == ["AAA", "BBB", "CCC"]
        assert len(corr["matrix"]) == 3
        # Diagonal is 1.0
        for i in range(3):
            assert corr["matrix"][i][i] == pytest.approx(1.0, abs=0.01)

    def test_portfolio_beta_returns_plain_float(self, patch_sources):
        bars = {
            "AAA": _make_bars(260, 0.002, 7),
            "SPY": _make_bars(260, 0.001, 99),
        }
        patch_sources(bars, {"AAA": "Tech"})
        result = pm.analyze_portfolio([{"symbol": "AAA", "shares": 1}])
        beta = result["portfolio"]["beta_vs_spy"]
        # Must be a plain Python float for JSON serialization
        assert beta is None or isinstance(beta, float)

    def test_empty_holdings_returns_error(self):
        assert pm.analyze_portfolio([])["error"] == "no holdings provided"

    def test_sector_weights_sum_to_approx_one(self, patch_sources):
        bars = {
            "AAA": _make_bars(120, 0.001, 8),
            "BBB": _make_bars(120, 0.001, 9),
            "CCC": _make_bars(120, 0.001, 10),
            "SPY": _make_bars(120, 0.0005, 99),
        }
        patch_sources(bars, {"AAA": "Tech", "BBB": "Tech", "CCC": "Health"})
        result = pm.analyze_portfolio([
            {"symbol": "AAA", "shares": 10},
            {"symbol": "BBB", "shares": 5},
            {"symbol": "CCC", "shares": 3},
        ])
        weights = result["sector_weights"]
        assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)
        assert weights["Tech"] > weights["Health"]  # more Tech shares/value
