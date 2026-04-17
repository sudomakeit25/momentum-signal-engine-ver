"""Unit tests for multi_year_trends helpers."""

import math

import numpy as np
import pandas as pd
import pytest

from src.scanner import multi_year_trends as mt


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2020-01-01", periods=len(values), freq="W")
    return pd.Series(values, index=idx, dtype=float)


class TestPctReturn:
    def test_basic(self):
        s = _series([100.0] + [0] * 51 + [110.0])
        s.iloc[1:-1] = np.linspace(100, 110, 51)
        r = mt._pct_return(s, 52)
        assert r == pytest.approx(10.0, abs=0.1)

    def test_too_short(self):
        assert mt._pct_return(_series([100, 101, 102]), 10) is None

    def test_zero_start_rejected(self):
        # lookback=2 on [0, 50, 100] picks start=iloc[-3]=0, which should
        # be rejected (no meaningful % return from a zero base).
        s = _series([0.0, 50.0, 100.0])
        assert mt._pct_return(s, 2) is None


class TestCagr:
    def test_doubling_in_one_year(self):
        s = _series([100.0, 200.0])
        c = mt._cagr(s, 1)
        assert c == pytest.approx(100.0, abs=0.01)

    def test_negative_years_returns_none(self):
        assert mt._cagr(_series([100, 120]), -1) is None

    def test_too_short(self):
        assert mt._cagr(_series([100]), 1) is None


class TestMaxDrawdown:
    def test_peak_to_trough(self):
        s = _series([100, 120, 60, 80])
        dd = mt._max_drawdown(s)
        assert dd == pytest.approx(-50.0, abs=0.01)

    def test_monotonic_up_has_zero_dd(self):
        s = _series([100, 110, 120, 130])
        assert mt._max_drawdown(s) == pytest.approx(0.0, abs=0.01)


class TestAnnualizedVol:
    def test_flat_series_has_zero_vol(self):
        s = _series([100.0] * 52)
        assert mt._annualized_vol(s) == pytest.approx(0.0, abs=0.001)

    def test_volatile_series_is_positive(self):
        rng = np.random.default_rng(1)
        s = _series(list(100 * np.cumprod(1 + rng.normal(0, 0.05, 104))))
        assert mt._annualized_vol(s) > 10  # >10% annualized


class TestRegime:
    def test_secular_uptrend(self):
        s = _series(list(np.linspace(50, 150, 120)))
        assert mt._regime(s) == "secular_uptrend"

    def test_secular_downtrend(self):
        s = _series(list(np.linspace(150, 50, 120)))
        assert mt._regime(s) == "secular_downtrend"

    def test_insufficient_history(self):
        assert mt._regime(_series([100.0] * 40)) == "insufficient_history"
