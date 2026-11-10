'''Profile screener caching when Yahoo Finance refuses the server.'''

import pytest

from src.scanner import profile_screener as ps

ROW = {"ticker": "NVDA", "name": "NVIDIA", "price": 100.0, "cap": 5_000_000_000, "fwd_pe": 20.0,
       "trail_pe": 30.0, "chg_6m": 10.0, "high_6m": 110.0, "low_6m": 80.0, "rev_growth": 50.0,
       "sector": "Technology", "industry": "Semiconductors"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    ps._cache.clear(); ps._last_good.clear(); ps._last_error.clear()
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(ps.time, "time", lambda: clock["t"])
    yield clock


def fetcher(monkeypatch, answers):
    calls = {"n": 0}
    def fake(tickers):
        i = min(calls["n"], len(answers) - 1)
        calls["n"] += 1
        rows = answers[i]
        monkeypatch.setattr(ps, "_fetch_error", "" if rows else "YFRateLimitError")
        return [dict(r) for r in rows]
    monkeypatch.setattr(ps, "_fetch_all", fake)
    return calls


def test_good_rows_are_cached_for_thirty_minutes(monkeypatch, _clean):
    calls = fetcher(monkeypatch, [[ROW]])
    assert len(ps.screen("semiconductors")) == 1
    _clean["t"] += 29 * 60
    ps.screen("semiconductors")
    assert calls["n"] == 1
    _clean["t"] += 2 * 60
    ps.screen("semiconductors")
    assert calls["n"] == 2


def test_empty_answer_is_retried_after_two_minutes_not_thirty(monkeypatch, _clean):
    calls = fetcher(monkeypatch, [[], [ROW]])
    assert ps.screen("semiconductors") == []
    assert ps.last_load_meta("semiconductors")["data_ok"] is False
    _clean["t"] += 60
    ps.screen("semiconductors")
    assert calls["n"] == 1                      # not hammering inside 2 minutes
    _clean["t"] += 90
    assert len(ps.screen("semiconductors")) == 1
    assert calls["n"] == 2 and ps.last_load_meta("semiconductors")["data_ok"] is True


def test_last_good_rows_are_served_when_the_source_goes_away(monkeypatch, _clean):
    fetcher(monkeypatch, [[ROW], []])
    ps.screen("semiconductors")
    _clean["t"] += 45 * 60
    rows = ps.screen("semiconductors")
    meta = ps.last_load_meta("semiconductors")
    assert [r["ticker"] for r in rows] == ["NVDA"]
    assert meta["data_ok"] is False and meta["stale_minutes"] == 45
    assert "YFRateLimitError" in meta["note"] and "45 min ago" in meta["note"]


def test_no_data_at_all_says_so(monkeypatch, _clean):
    fetcher(monkeypatch, [[]])
    assert ps.screen("mega_cap") == []
    meta = ps.last_load_meta("mega_cap")
    assert meta == {"data_ok": False, "stale_minutes": 0,
                    "note": "Yahoo Finance is not answering (YFRateLimitError); no data to show yet."}


def test_filters_still_apply_and_an_empty_match_is_not_a_data_failure(monkeypatch, _clean):
    fetcher(monkeypatch, [[ROW]])
    assert ps.screen("semiconductors", max_fwd_pe=5) == []
    assert ps.last_load_meta("semiconductors")["data_ok"] is True


def test_warm_cache_reports_zero_and_does_not_poison_the_cache(monkeypatch, _clean):
    calls = fetcher(monkeypatch, [[]])
    assert ps.warm_cache(("semiconductors",)) == 0
    _clean["t"] += 3 * 60
    ps.warm_cache(("semiconductors",))
    assert calls["n"] == 2                      # retried, not stuck for 30 minutes


def test_failures_are_logged_once_as_a_warning(monkeypatch):
    import sys, types
    class Boom(Exception): pass
    fake = types.SimpleNamespace(
        download=lambda *a, **k: None,
        Ticker=lambda t: (_ for _ in ()).throw(Boom("429")),
    )
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    warned = []
    monkeypatch.setattr(ps.logger, "warning", lambda msg, *a: warned.append(msg % a))
    assert ps._fetch_all(["A", "B", "C"]) == []
    assert warned == ["profile screener: 3 of 3 tickers failed (Boom)"]
    assert ps._fetch_error == "Boom"


def test_fetch_error_reaches_the_note_through_the_real_path(monkeypatch, _clean):
    import sys, types
    class YFRateLimitError(Exception): pass
    fake = types.SimpleNamespace(
        download=lambda *a, **k: None,
        Ticker=lambda t: (_ for _ in ()).throw(YFRateLimitError("Too Many Requests")),
    )
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    assert ps.screen("mega_cap") == []
    assert "YFRateLimitError" in ps.last_load_meta("mega_cap")["note"]


def test_route_reports_data_status(monkeypatch, _clean):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.routes import router
    fetcher(monkeypatch, [[]])
    app = FastAPI(); app.include_router(router)
    body = TestClient(app).get("/profile-screener/run?sector=semiconductors").json()
    assert body["count"] == 0 and body["data_ok"] is False and "Yahoo Finance" in body["note"]
