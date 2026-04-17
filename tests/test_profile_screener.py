"""Unit tests for profile_screener.screen filtering (seeded cache, no network)."""

import time

import pytest

from src.scanner import profile_screener as ps


def _row(ticker: str, **overrides) -> dict:
    base = {
        "ticker": ticker,
        "name": ticker,
        "price": 100.0,
        "cap": 10_000_000_000,
        "fwd_pe": 20.0,
        "trail_pe": 25.0,
        "chg_6m": 10.0,
        "high_6m": 110.0,
        "low_6m": 80.0,
        "rev_growth": 15.0,
        "sector": "Technology",
        "industry": "Semiconductors",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_cache():
    ps._cache.clear()
    yield
    ps._cache.clear()


def _seed(sector: str, rows: list[dict]) -> None:
    tickers = ps.SECTORS[sector]
    key = f"{sector}:{','.join(sorted(tickers))}"
    ps._cache[key] = (time.time(), rows)


class TestMetadata:
    def test_list_profiles_contains_like_mu(self):
        keys = {p["key"] for p in ps.list_profiles()}
        assert "like_mu" in keys
        assert "custom" in keys

    def test_list_sectors_has_semiconductors(self):
        assert "semiconductors" in ps.list_sectors()


class TestFiltering:
    def test_no_filters_returns_everything_sorted_by_pe(self):
        _seed("semiconductors", [
            _row("AAA", fwd_pe=30.0),
            _row("BBB", fwd_pe=5.0),
            _row("CCC", fwd_pe=15.0),
            _row("DDD", fwd_pe=None),  # None sorted last
        ])
        rows = ps.screen(sector="semiconductors")
        tickers = [r["ticker"] for r in rows]
        assert tickers == ["BBB", "CCC", "AAA", "DDD"]

    def test_max_fwd_pe_rejects_null_and_too_high(self):
        _seed("semiconductors", [
            _row("LOW", fwd_pe=10.0),
            _row("HIGH", fwd_pe=40.0),
            _row("NULL", fwd_pe=None),
            _row("ZERO", fwd_pe=0),
        ])
        rows = ps.screen(sector="semiconductors", max_fwd_pe=15)
        assert [r["ticker"] for r in rows] == ["LOW"]

    def test_min_cap_filters_small_companies(self):
        _seed("semiconductors", [
            _row("BIG", cap=20_000_000_000),
            _row("SMALL", cap=1_000_000_000),
        ])
        rows = ps.screen(sector="semiconductors", min_cap=5_000_000_000)
        assert [r["ticker"] for r in rows] == ["BIG"]

    def test_min_rev_growth(self):
        _seed("semiconductors", [
            _row("FAST", rev_growth=40.0),
            _row("SLOW", rev_growth=5.0),
        ])
        rows = ps.screen(sector="semiconductors", min_rev_growth=20)
        assert [r["ticker"] for r in rows] == ["FAST"]

    def test_min_momentum(self):
        _seed("semiconductors", [
            _row("HOT", chg_6m=50.0),
            _row("COLD", chg_6m=-5.0),
        ])
        rows = ps.screen(sector="semiconductors", min_momentum_6m=20)
        assert [r["ticker"] for r in rows] == ["HOT"]

    def test_combined_filters_like_mu_profile(self):
        _seed("semiconductors", [
            _row("MU", fwd_pe=5.0, cap=100_000_000_000, rev_growth=100.0),
            _row("EXPENSIVE", fwd_pe=40.0, cap=100_000_000_000, rev_growth=100.0),
            _row("SMALL", fwd_pe=5.0, cap=1_000_000_000, rev_growth=100.0),
            _row("FLAT", fwd_pe=5.0, cap=100_000_000_000, rev_growth=2.0),
        ])
        rows = ps.screen(
            sector="semiconductors",
            max_fwd_pe=15,
            min_rev_growth=20,
            min_cap=5_000_000_000,
        )
        assert [r["ticker"] for r in rows] == ["MU"]


class TestCacheBehavior:
    def test_custom_tickers_uses_separate_cache_key(self, monkeypatch):
        calls = {"count": 0}

        def fake_fetch(tickers):
            calls["count"] += 1
            return [_row(t) for t in tickers]

        monkeypatch.setattr(ps, "_fetch_all", fake_fetch)

        ps.screen(custom_tickers="AAA,BBB")
        ps.screen(custom_tickers="AAA,BBB")  # second call cache hit
        assert calls["count"] == 1

        ps.screen(custom_tickers="AAA,CCC")  # different set -> refetch
        assert calls["count"] == 2
