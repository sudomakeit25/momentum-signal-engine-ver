"""FINRA short-volume batch: same answer as before while holding only one
daily report at a time (all of them at once added about 150 MB on the host
on 2026-11-11), and a cache key that names the symbols. No network."""

from datetime import datetime as real_datetime

import pytest

from src.data import finra_client as fc

NOW = real_datetime(2026, 11, 11, 18, 0)        # a Wednesday
REAL_FETCH = fc._fetch_daily_report             # kept before the fixture replaces it


class _FixedDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


class _MemCache:
    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v


def _report(day: int) -> dict:
    """A small fake daily report whose numbers depend on the day."""
    return {
        "GME": {"short_volume": 100 + day, "short_exempt_volume": 1, "total_volume": 400},
        "AMC": {"short_volume": 50, "short_exempt_volume": 0, "total_volume": 0},
        "RIOT": {"short_volume": 10 * day, "short_exempt_volume": 2, "total_volume": 1000},
    }


@pytest.fixture(autouse=True)
def wire(monkeypatch):
    monkeypatch.setattr(fc, "datetime", _FixedDatetime)
    monkeypatch.setattr(fc, "_cache", _MemCache())
    fetched = []

    def fake_fetch(date):
        fetched.append(date.date())
        if date.day == 6:                       # a day FINRA has no report for
            return {}
        return _report(date.day)

    monkeypatch.setattr(fc, "_fetch_daily_report", fake_fetch)
    return fetched


def _reference(symbols, days):
    """The previous implementation's answer, computed independently."""
    reports, date, attempts = [], NOW, 0
    from datetime import timedelta
    while len(reports) < days and attempts < days * 2:
        date -= timedelta(days=1)
        attempts += 1
        if date.weekday() >= 5:
            continue
        rep = {} if date.day == 6 else _report(date.day)
        if rep:
            reports.append((date, rep))
    reports.reverse()
    out = {}
    for s in symbols:
        rows = [{"date": d.isoformat(), "short_volume": r[s.upper()]["short_volume"],
                 "short_exempt_volume": r[s.upper()]["short_exempt_volume"],
                 "total_volume": r[s.upper()]["total_volume"],
                 "short_pct": round(r[s.upper()]["short_volume"] / r[s.upper()]["total_volume"] * 100, 2)
                 if r[s.upper()]["total_volume"] > 0 else 0}
                for d, r in reports if s.upper() in r]
        if rows:
            out[s] = rows
    return out


class TestSameAnswer:
    @pytest.mark.parametrize("symbols", [["GME", "AMC", "RIOT"], ["riot", "GME"], ["ZZZZ", "GME"], ["AMC"]])
    def test_matches_the_previous_implementation(self, symbols):
        assert fc.get_short_volume_batch(symbols, days=5) == _reference(symbols, 5)

    def test_oldest_first_and_skips_weekends_and_missing_days(self, wire):
        out = fc.get_short_volume_batch(["GME"], days=5)
        dates = [e["date"][:10] for e in out["GME"]]
        assert dates == sorted(dates) and len(dates) == 5
        assert all(real_datetime.fromisoformat(d).weekday() < 5 for d in dates)
        assert "2026-11-06" not in dates                 # no report that day
        assert all(d.weekday() < 5 for d in wire)       # never asked for a weekend

    def test_zero_total_volume_gives_zero_percent(self):
        assert all(e["short_pct"] == 0 for e in fc.get_short_volume_batch(["AMC"], days=3)["AMC"])

    def test_repeated_symbol_is_not_counted_twice(self):
        out = fc.get_short_volume_batch(["GME", "GME"], days=4)
        assert len(out["GME"]) == 4

    def test_unknown_symbols_and_empty_input(self):
        assert fc.get_short_volume_batch(["ZZZZ"], days=3) == {}
        assert fc.get_short_volume_batch([], days=3) == {}

    def test_no_reports_at_all(self, monkeypatch):
        monkeypatch.setattr(fc, "_fetch_daily_report", lambda d: {})
        assert fc.get_short_volume_batch(["GME"], days=3) == {}


class TestCacheKey:
    def test_different_lists_of_the_same_length_do_not_share_an_answer(self):
        first = fc.get_short_volume_batch(["GME", "AMC"], days=3)
        second = fc.get_short_volume_batch(["RIOT", "AMC"], days=3)
        assert "RIOT" in second and "GME" not in second and "GME" in first

    def test_same_list_in_another_order_or_case_reuses_the_answer(self, wire):
        fc.get_short_volume_batch(["GME", "AMC"], days=3)
        n = len(wire)
        fc.get_short_volume_batch(["amc", "gme"], days=3)
        assert len(wire) == n


class TestPages:
    def test_pages_are_summed_across_facilities(self):
        result = {}
        fc._aggregate_short_volume(result, [
            {"securitiesInformationProcessorSymbolIdentifier": "GME", "shortParQuantity": 10,
             "shortExemptParQuantity": 1, "totalParQuantity": 40},
            {"securitiesInformationProcessorSymbolIdentifier": "", "shortParQuantity": 99},
        ])
        fc._aggregate_short_volume(result, [
            {"securitiesInformationProcessorSymbolIdentifier": "GME", "shortParQuantity": 5,
             "shortExemptParQuantity": 0, "totalParQuantity": 10},
        ])
        assert result == {"GME": {"short_volume": 15, "short_exempt_volume": 1, "total_volume": 50}}

    def test_daily_report_folds_each_page_as_it_arrives(self, monkeypatch):
        row = {"securitiesInformationProcessorSymbolIdentifier": "GME", "shortParQuantity": 1,
               "shortExemptParQuantity": 0, "totalParQuantity": 2}
        pages = [[row] * 5000, [row] * 3]

        class Resp:
            status_code = 200

            def __init__(self, rows):
                self.rows = rows

            def json(self):
                return self.rows

        monkeypatch.setattr(fc.requests, "post", lambda *a, **k: Resp(pages.pop(0)))
        out = REAL_FETCH(real_datetime(2026, 11, 10))
        assert out == {"GME": {"short_volume": 5003, "short_exempt_volume": 0, "total_volume": 10006}}
