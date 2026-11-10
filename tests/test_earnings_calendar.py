"""Tests for the earnings sources: Nasdaq calendar (primary), FMP per symbol
(fallback), and the FMP stable-API migration. No network: requests.get is
replaced in every test."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.data import earnings_calendar as ec
from src.data import fmp_client as fmp

ET = ZoneInfo("America/New_York")
TUE = datetime(2026, 11, 10, 11, 0, tzinfo=ET)


class Resp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code = status
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def nasdaq_body(symbols, code=200):
    rows = None if symbols is None else [{"symbol": s, "time": "time-after-hours"} for s in symbols]
    return {"data": {"rows": rows}, "status": {"rCode": code}}


class NoCache:
    def __init__(self):
        self.store = {}
    def get(self, key):
        return self.store.get(key)
    def set(self, key, value):
        self.store[key] = value


class Limiter:
    def __init__(self, allow=True):
        self.allow, self.used = allow, 0
    def try_acquire(self):
        self.used += 1
        return self.allow


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from config.settings import settings
    ec._day_cache.clear()
    ec._last.update(source="", nasdaq={}, at="")
    fmp._outcomes.clear()
    fmp._symbol_refused.clear()
    monkeypatch.setattr(fmp, "_cache", NoCache())
    monkeypatch.setattr(fmp, "_limiter", Limiter())
    monkeypatch.setattr(settings, "fmp_api_key", "test-key-123")
    yield


def route(monkeypatch, nasdaq=None, fmp_handler=None):
    """Install a fake requests.get for both modules. `nasdaq` maps a date
    string to a Resp (or raises if it is an Exception)."""
    calls = {"nasdaq": [], "fmp": []}

    # Both modules use the same `requests` object, so one fake dispatches on
    # the host.
    def fake_get(url, params=None, headers=None, timeout=None):
        if "api.nasdaq.com" in url:
            calls["nasdaq"].append(params["date"])
            assert "Mozilla" in headers["User-Agent"]
            out = (nasdaq or {}).get(params["date"], Resp(500))
            if isinstance(out, Exception):
                raise out
            return out
        assert "financialmodelingprep.com" in url, url
        calls["fmp"].append((url, dict(params)))
        return fmp_handler(url, params) if fmp_handler else Resp(500)

    assert ec.requests is fmp.requests
    monkeypatch.setattr(ec.requests, "get", fake_get)
    return calls


# ------------------------------------------------------------------- Nasdaq

class TestNasdaq:
    def test_reporting_today_or_tomorrow_and_everything_is_known(self, monkeypatch):
        route(monkeypatch, {"2026-11-10": Resp(body=nasdaq_body(["asts", "TDG"])),
                            "2026-11-11": Resp(body=nasdaq_body(["CSCO"]))})
        reporting, known = ec.reporting_soon(["ASTS", "CSCO", "NVDA"], now=TUE)
        assert reporting == {"ASTS", "CSCO"}
        assert known == {"ASTS", "CSCO", "NVDA"}
        assert ec.status()["source"] == "nasdaq"

    def test_no_earnings_on_a_date_is_a_real_answer(self, monkeypatch):
        route(monkeypatch, {"2026-11-10": Resp(body=nasdaq_body(None)),
                            "2026-11-11": Resp(body=nasdaq_body([]))})
        assert ec.reporting_soon(["NVDA"], now=TUE) == (set(), {"NVDA"})

    def test_symbols_are_compared_case_insensitively(self, monkeypatch):
        route(monkeypatch, {"2026-11-10": Resp(body=nasdaq_body(["NVDA"])),
                            "2026-11-11": Resp(body=nasdaq_body([]))})
        assert ec.reporting_soon(["nvda"], now=TUE)[0] == {"NVDA"}

    def test_empty_symbol_list_makes_no_request(self, monkeypatch):
        calls = route(monkeypatch)
        assert ec.reporting_soon([], now=TUE) == (set(), set())
        assert calls["nasdaq"] == []

    @pytest.mark.parametrize("bad", [
        Resp(403), Resp(500), Resp(200, body=None), Resp(200, body=["not", "a", "dict"]),
        Resp(200, body={"data": None, "status": {"rCode": 200}}),
        Resp(200, body=nasdaq_body(["X"], code=400)),
        Resp(200, body={"data": {"rows": "oops"}, "status": {"rCode": 200}}),
        TimeoutError("timed out"),
    ])
    def test_any_failure_is_unknown_not_clear(self, monkeypatch, bad):
        route(monkeypatch, {"2026-11-10": bad, "2026-11-11": Resp(body=nasdaq_body([]))})
        assert ec.nasdaq_day(TUE.date()) is None
        reporting, known = ec.reporting_soon(["NVDA"], now=TUE)   # FMP fallback also down
        assert reporting == set() and known == set()
        per_day = ec.status()["nasdaq"]
        assert per_day["2026-11-10"]["ok"] is False and per_day["2026-11-11"]["ok"] is True

    def test_one_bad_day_is_enough_to_distrust_the_calendar(self, monkeypatch):
        route(monkeypatch, {"2026-11-10": Resp(body=nasdaq_body([])), "2026-11-11": Resp(503)})
        assert ec.reporting_soon(["NVDA"], now=TUE) == (set(), set())

    def test_success_is_cached_and_failure_is_retried_later(self, monkeypatch):
        calls = route(monkeypatch, {"2026-11-10": Resp(body=nasdaq_body(["A"])),
                                    "2026-11-11": Resp(503)})
        clock = {"t": 1_000_000.0}
        monkeypatch.setattr(ec.time, "time", lambda: clock["t"])
        ec.reporting_soon(["A"], now=TUE)
        ec.reporting_soon(["A"], now=TUE)
        assert calls["nasdaq"] == ["2026-11-10", "2026-11-11"]         # both cached
        clock["t"] += ec._FAIL_TTL + 1
        ec.reporting_soon(["A"], now=TUE)
        assert calls["nasdaq"] == ["2026-11-10", "2026-11-11", "2026-11-11"]   # only the failed day


# ------------------------------------------------------------- FMP fallback

def fmp_symbol_handler(table):
    """table: symbol -> Resp"""
    def handler(url, params):
        assert url.endswith("/stable/earnings")
        return table.get(params["symbol"], Resp(500))
    return handler


class TestFmpFallback:
    def test_used_only_when_nasdaq_is_down_and_known_is_per_symbol(self, monkeypatch):
        calls = route(
            monkeypatch,
            nasdaq={},   # every date 500
            fmp_handler=fmp_symbol_handler({
                "NVDA": Resp(body=[{"date": "2026-11-11", "epsActual": None},
                                   {"date": "2026-08-20", "epsActual": 1.0}]),
                "AAPL": Resp(body=[{"date": "2027-02-04", "epsActual": None}]),
                "ASTS": Resp(402, body={"Error Message": "Premium Query Parameter"}),
            }),
        )
        reporting, known = ec.reporting_soon(["NVDA", "AAPL", "ASTS"], now=TUE)
        assert reporting == {"NVDA"}
        assert known == {"NVDA", "AAPL"}            # ASTS refused: unknown, not clear
        assert ec.status()["source"].startswith("fmp")
        assert len(calls["fmp"]) == 3

    def test_not_called_when_nasdaq_answers(self, monkeypatch):
        calls = route(monkeypatch, {"2026-11-10": Resp(body=nasdaq_body([])),
                                    "2026-11-11": Resp(body=nasdaq_body([]))})
        ec.reporting_soon(["NVDA"], now=TUE)
        assert calls["fmp"] == []

    def test_fallback_is_capped(self, monkeypatch):
        calls = route(monkeypatch, nasdaq={},
                      fmp_handler=lambda url, params: Resp(body=[]))
        many = [f"S{i}" for i in range(80)]
        _, known = ec.reporting_soon(many, now=TUE)
        assert len(calls["fmp"]) == ec._MAX_FMP_FALLBACK and len(known) == ec._MAX_FMP_FALLBACK


class TestFmpSymbolEarnings:
    def _today(self):
        return datetime.now().strftime("%Y-%m-%d")

    def test_next_unreported_date(self, monkeypatch):
        route(monkeypatch, fmp_handler=lambda u, p: Resp(body=[
            {"date": "2099-05-01", "epsActual": None}, {"date": "2099-02-01", "epsActual": None},
            {"date": "2000-01-01", "epsActual": None},      # stale row with no actual
            {"date": "2099-01-01", "epsActual": 2.0},       # already reported
        ]))
        assert fmp.get_symbol_next_earnings("nvda") == (True, "2099-02-01")

    def test_no_upcoming_date_is_still_known(self, monkeypatch):
        route(monkeypatch, fmp_handler=lambda u, p: Resp(body=[]))
        assert fmp.get_symbol_next_earnings("NVDA") == (True, None)

    def test_plan_refusal_is_remembered_for_the_day(self, monkeypatch):
        calls = route(monkeypatch, fmp_handler=lambda u, p: Resp(
            402, body={"Error Message": "not available under your current subscription"}))
        assert fmp.get_symbol_next_earnings("ASTS") == (False, None)
        assert fmp.get_symbol_next_earnings("ASTS") == (False, None)
        assert len(calls["fmp"]) == 1               # second call cost nothing

    def test_transient_error_is_not_remembered(self, monkeypatch):
        calls = route(monkeypatch, fmp_handler=lambda u, p: Resp(500))
        fmp.get_symbol_next_earnings("NVDA")
        fmp.get_symbol_next_earnings("NVDA")
        assert len(calls["fmp"]) == 2

    def test_no_key_or_rate_limit_is_unknown(self, monkeypatch):
        from config.settings import settings
        calls = route(monkeypatch, fmp_handler=lambda u, p: Resp(body=[]))
        monkeypatch.setattr(fmp, "_limiter", Limiter(allow=False))
        assert fmp.get_symbol_next_earnings("NVDA") == (False, None)
        monkeypatch.setattr(settings, "fmp_api_key", "")
        assert fmp.get_symbol_next_earnings("NVDA") == (False, None)
        assert calls["fmp"] == []


# ------------------------------------------------- FMP stable-API migration

class TestFmpStable:
    def test_earnings_calendar_uses_stable_and_normalizes(self, monkeypatch):
        calls = route(monkeypatch, fmp_handler=lambda u, p: Resp(body=[
            {"symbol": "nvda", "date": "2026-11-17", "epsActual": None, "epsEstimated": 2.47,
             "revenueActual": None, "revenueEstimated": 5.0e10, "lastUpdated": "2026-11-09"},
            {"symbol": "OLD", "date": "2026-11-18 00:00:00", "eps": 1.0, "revenue": 9.0,
             "time": "amc"},                                   # legacy field names
            {"date": "2026-11-18"}, "junk", {"symbol": "X"},   # unusable rows
        ]))
        rows = fmp.get_earnings_calendar(days_ahead=14)
        url, params = calls["fmp"][0]
        assert url == "https://financialmodelingprep.com/stable/earnings-calendar"
        assert set(params) == {"from", "to", "apikey"}
        assert rows == [
            {"symbol": "NVDA", "date": "2026-11-17", "eps": None, "epsEstimated": 2.47,
             "revenue": None, "revenueEstimated": 5.0e10, "time": ""},
            {"symbol": "OLD", "date": "2026-11-18", "eps": 1.0, "epsEstimated": None,
             "revenue": 9.0, "revenueEstimated": None, "time": "amc"},
        ]

    def test_calendar_rows_feed_the_existing_earnings_page_parser(self, monkeypatch):
        from src.scanner.earnings_whisper import get_upcoming_earnings
        route(monkeypatch, fmp_handler=lambda u, p: Resp(body=[
            {"symbol": "NVDA", "date": "2026-11-17", "epsEstimated": 2.47}]))
        events = get_upcoming_earnings(["NVDA", "AMD"], days_ahead=14)
        assert [(e.symbol, e.date.strftime("%Y-%m-%d"), e.eps_estimate, e.time) for e in events] == \
            [("NVDA", "2026-11-17", 2.47, "unknown")]

    @pytest.mark.parametrize("resp", [
        Resp(402, body={"Error Message": "Restricted Endpoint"}),
        Resp(403, body={"Error Message": "legacy users only"}),
        Resp(200, body={"Error Message": "Invalid API KEY."}),      # error with HTTP 200
        Resp(200, body={"unexpected": "object"}),
        Resp(500, body=None, text="<html>bad gateway</html>"),
    ])
    def test_refusals_return_empty_and_are_recorded(self, monkeypatch, resp):
        route(monkeypatch, fmp_handler=lambda u, p: resp)
        assert fmp.get_earnings_calendar(days_ahead=1) == []
        seen = fmp.status()["endpoints"]["/earnings-calendar"]
        if resp.status_code != 200 or (isinstance(resp._body, dict) and "Error Message" in resp._body):
            assert seen["ok"] is False

    def test_status_never_contains_the_key(self, monkeypatch):
        route(monkeypatch, fmp_handler=lambda u, p: Resp(
            401, body={"Error Message": "Invalid API KEY test-key-123 supplied"}))
        fmp.get_earnings_calendar(days_ahead=1)
        s = fmp.status()
        assert s["configured"] is True
        assert "test-key-123" not in str(s) and "***" in s["endpoints"]["/earnings-calendar"]["message"]

    def test_network_error_is_recorded(self, monkeypatch):
        def boom(u, p):
            raise ConnectionError("dns")
        route(monkeypatch, fmp_handler=boom)
        assert fmp.get_earnings_calendar(days_ahead=1) == []
        assert fmp.status()["endpoints"]["/earnings-calendar"]["status"] == 0

    def test_screener_pages_and_dedupes(self, monkeypatch):
        monkeypatch.setattr(fmp, "_SCREEN_PAGE", 3)
        pages = {0: ["A", "B", "C"], 1: ["C", "D", "E"], 2: ["F"]}
        calls = route(monkeypatch, fmp_handler=lambda u, p: Resp(
            body=[{"symbol": s} for s in pages.get(p["page"], [])]))
        rows = fmp.screen_companies({"exchange": "NASDAQ"})
        assert [r["symbol"] for r in rows] == ["A", "B", "C", "D", "E", "F"]
        assert calls["fmp"][0][0].endswith("/stable/company-screener")
        assert [c[1]["page"] for c in calls["fmp"]] == [0, 1, 2]

    def test_screener_that_ignores_paging_cannot_loop(self, monkeypatch):
        monkeypatch.setattr(fmp, "_SCREEN_PAGE", 2)
        calls = route(monkeypatch, fmp_handler=lambda u, p: Resp(
            body=[{"symbol": "A"}, {"symbol": "B"}]))        # same page every time
        assert len(fmp.screen_companies({})) == 2
        assert len(calls["fmp"]) == 2

    def test_screener_refused_returns_none_and_universe_falls_back(self, monkeypatch):
        route(monkeypatch, fmp_handler=lambda u, p: Resp(
            402, body={"Error Message": "Restricted Endpoint"}))
        assert fmp.screen_companies({"exchange": "NYSE"}) is None
        monkeypatch.setattr(fmp, "_universe_cache", None)
        assert fmp.get_liquid_universe(force_refresh=True) == []   # caller uses its hardcoded list
        assert "Restricted" in fmp.status()["endpoints"]["/company-screener"]["message"]

    def test_universe_merges_exchanges_and_filters_odd_symbols(self, monkeypatch):
        by_exchange = {"NYSE": ["JPM", "BRK.B"], "NASDAQ": ["NVDA", "aapl"], "AMEX": ["SPY", "X-Y"]}
        route(monkeypatch, fmp_handler=lambda u, p: Resp(
            body=[{"symbol": s} for s in by_exchange[p["exchange"]]] if p["page"] == 0 else []))
        monkeypatch.setattr(fmp, "_universe_cache", None)
        assert fmp.get_liquid_universe(force_refresh=True) == ["AAPL", "JPM", "NVDA", "SPY"]


class TestHealthRoute:
    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api import routes
        routes._data_probe_at = 0.0
        app = FastAPI()
        app.include_router(routes.router)
        return TestClient(app)

    def test_reports_sources_without_probing(self, monkeypatch):
        calls = route(monkeypatch)
        r = self._client().get("/health/data")
        assert r.status_code == 200 and r.json()["probed"] is None
        assert calls["nasdaq"] == [] and calls["fmp"] == []
        assert "test-key-123" not in r.text

    def test_probe_runs_once_a_minute(self, monkeypatch):
        today = datetime.now(tz=ET).date()
        calls = route(monkeypatch, {d.isoformat(): Resp(body=nasdaq_body(["MU"]))
                                    for d in (today, today.fromordinal(today.toordinal() + 1))})
        c = self._client()
        first = c.get("/health/data?probe=true").json()
        assert first["probed"] == {"asked": ["NVDA", "AAPL", "MU"],
                                   "known": ["AAPL", "MU", "NVDA"], "reporting": ["MU"]}
        assert first["earnings"]["source"] == "nasdaq"
        assert c.get("/health/data?probe=true").json()["probed"] is None    # throttled
        assert len(calls["nasdaq"]) == 2
