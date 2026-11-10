"""Scorecard (src/scanner/scorecard.py): logging, outcomes, summary. No network."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.scanner import scorecard as sc

ET = ZoneInfo("America/New_York")
MON_10 = datetime(2026, 11, 9, 10, 0, tzinfo=ET)


class FakeRedis:
    def __init__(self):
        self.data, self.fail_get, self.fail_set = {}, False, False
    def get(self, k):
        if self.fail_get:
            raise TimeoutError()
        return self.data.get(k)
    def set(self, k, v):
        if self.fail_set:
            raise TimeoutError()
        self.data[k] = v


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(sc, "_get_redis", lambda: None)
    monkeypatch.setattr(sc, "_mem", None)
    monkeypatch.setattr(sc, "_last_refresh", 0.0)
    # Fixed dates are used throughout; do not let the retention window make
    # these tests depend on the day they are run.
    monkeypatch.setattr(sc, "_KEEP_DAYS", 100_000)
    yield


def alert(symbol="NVDA", kind="higher_low", direction="up", price=100.0, **kw):
    return {"symbol": symbol, "kind": kind, "direction": direction, "price": price, **kw}


def five_min(day: date, closes, start=(9, 30), highs=None, lows=None):
    t0 = datetime(day.year, day.month, day.day, *start, tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=5 * i) for i in range(len(closes))])
    return pd.DataFrame({"open": closes, "high": highs or closes, "low": lows or closes,
                         "close": closes, "volume": 1000}, index=idx)


def daily(pairs):
    """pairs: [(date, close)], stamped the way Alpaca stamps daily bars."""
    idx = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=5) for d, _ in pairs])
    closes = [c for _, c in pairs]
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes,
                         "volume": 1000}, index=idx)


def weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# ------------------------------------------------------------------ logging

class TestLogging:
    def test_logs_once_per_symbol_kind_direction_and_day(self):
        assert sc.log_alerts([alert(), alert()], now=MON_10) == 1
        assert sc.log_alerts([alert(price=105.0)], now=MON_10) == 0     # same day: kept as first seen
        assert sc.log_alerts([alert(kind="vwap_reclaim"), alert(direction="down")], now=MON_10) == 2
        assert sc.log_alerts([alert()], now=MON_10 + timedelta(days=1)) == 1
        recs = sc._load()
        assert len(recs) == 4 and recs[0]["price"] == 100.0
        assert recs[0]["id"] == "2026-11-09:NVDA:higher_low:up"

    def test_rejects_unusable_alerts(self):
        bad = [alert(direction="sideways"), alert(price=0), alert(price=None), alert(symbol=""),
               alert(kind=""), {"symbol": "X"}, alert(price="12")]
        assert sc.log_alerts(bad, now=MON_10) == 0 and sc._load() == []
        assert sc.log_alerts([], now=MON_10) == 0

    def test_uses_the_alert_time_when_given(self):
        sc.log_alerts([alert(time="2026-11-06T14:35:00-05:00")], now=MON_10)
        r = sc._load()[0]
        assert r["date"] == "2026-11-06" and r["ts"].startswith("2026-11-06T14:35:00")

    def test_naive_and_malformed_times(self):
        sc.log_alerts([alert(symbol="A", time="2026-11-06T14:35:00"),
                       alert(symbol="B", time="not a time")], now=MON_10)
        by = {r["symbol"]: r for r in sc._load()}
        assert by["A"]["date"] == "2026-11-06" and by["B"]["date"] == "2026-11-09"

    def test_from_signal(self):
        from src.data.models import SetupType, Signal, SignalAction
        s = Signal(symbol="NVDA", action=SignalAction.SELL, setup_type=SetupType.VWAP_REJECTION,
                   entry=100.0, stop_loss=101.0, target=98.0, rr_ratio=2.0, confidence=0.6,
                   timestamp=MON_10)
        a = sc.from_signal(s)
        assert (a["kind"], a["direction"], a["price"], a["stop"], a["target"]) == \
            ("vwap_rejection", "down", 100.0, 101.0, 98.0)
        assert sc.log_alerts([a]) == 1

    def test_old_records_and_overflow_are_trimmed(self, monkeypatch):
        monkeypatch.setattr(sc, "_MAX_RECORDS", 3)
        monkeypatch.setattr(sc, "_KEEP_DAYS", 90)
        today = datetime.now(tz=ET)
        sc.log_alerts([alert(symbol="OLD")], now=today - timedelta(days=200))
        assert sc._load() == []
        sc.log_alerts([alert(symbol=f"S{i}") for i in range(5)], now=today)
        assert [r["symbol"] for r in sc._load()] == ["S2", "S3", "S4"]

    def test_persists_to_redis_and_survives_a_restart(self, monkeypatch):
        r = FakeRedis()
        monkeypatch.setattr(sc, "_get_redis", lambda: r)
        sc.log_alerts([alert()], now=datetime.now(tz=ET))
        monkeypatch.setattr(sc, "_mem", None)                 # restart
        assert len(sc._load()) == 1

    def test_redis_failures_do_not_raise_or_lose_the_session_copy(self, monkeypatch):
        r = FakeRedis()
        monkeypatch.setattr(sc, "_get_redis", lambda: r)
        r.fail_set = True
        assert sc.log_alerts([alert()], now=datetime.now(tz=ET)) == 1
        r.fail_get = True
        assert len(sc._load()) == 1


# --------------------------------------------------------------- evaluation

def record(**kw):
    base = {"id": "x", "ts": "2026-11-09T10:00:00-05:00", "date": "2026-11-09", "symbol": "NVDA",
            "kind": "higher_low", "direction": "up", "price": 100.0, "stop": None,
            "target": None, "outcome": {}, "final": False}
    base.update(kw)
    return base


MON = date(2026, 11, 9)
LATER = date(2026, 11, 20)


class TestEvaluate:
    def test_all_horizons_long(self):
        # bars at 09:30 .. ; alert at 10:00 -> 10:15 is bar 9, 11:00 is bar 18
        closes = [100.0] * 9 + [101.0] + [100.5] * 8 + [103.0] + [102.0] * 5
        days = weekdays(MON, 7)
        d = daily([(days[0], 102.0), (days[1], 99.0), (days[2], 99.5), (days[3], 100.0),
                   (days[4], 104.0), (days[5], 106.0), (days[6], 107.0)])
        out = sc.evaluate(record(), five_min(MON, closes), d, LATER)
        assert out == {"m15": 1.0, "h1": 3.0, "eod": 2.0, "d1": -1.0, "d5": 6.0}

    def test_short_alerts_are_signed_so_a_fall_is_positive(self):
        closes = [100.0] * 9 + [98.0] + [98.0] * 14
        d = daily([(MON, 97.0)])
        out = sc.evaluate(record(direction="down"), five_min(MON, closes), d, LATER)
        assert out["m15"] == 2.0 and out["eod"] == 3.0

    def test_same_day_nothing_is_final_yet(self):
        closes = [100.0] * 9 + [101.0] * 3
        d = daily([(MON, 101.5)])                 # today's bar is still forming
        out = sc.evaluate(record(), five_min(MON, closes), d, today=MON)
        assert out == {"m15": 1.0}                # no eod / d1 until the session has closed

    def test_next_day_close_is_not_counted_until_that_day_is_over(self):
        days = weekdays(MON, 2)
        d = daily([(days[0], 102.0), (days[1], 105.0)])
        assert "d1" not in sc.evaluate(record(), None, d, today=days[1])
        assert sc.evaluate(record(), None, d, today=days[1] + timedelta(days=1))["d1"] == 5.0

    def test_alert_late_in_the_day_has_no_intraday_horizons(self):
        r = record(ts="2026-11-09T15:55:00-05:00")
        out = sc.evaluate(r, five_min(MON, [100.0] * 78), daily([(MON, 101.0)]), LATER)
        assert "m15" not in out and "h1" not in out and out["eod"] == 1.0

    def test_missing_data_yields_nothing_and_keeps_existing(self):
        assert sc.evaluate(record(), None, None, LATER) == {}
        assert sc.evaluate(record(), pd.DataFrame(), pd.DataFrame(), LATER) == {}
        kept = sc.evaluate(record(outcome={"m15": 9.9}), None, None, LATER)
        assert kept == {"m15": 9.9}

    def test_existing_values_are_not_recomputed(self):
        closes = [100.0] * 9 + [101.0] * 15
        out = sc.evaluate(record(outcome={"m15": -7.0}), five_min(MON, closes), None, LATER)
        assert out["m15"] == -7.0 and out["h1"] == 1.0

    def test_alert_date_missing_from_daily_bars(self):
        d = daily([(date(2026, 11, 2), 90.0), (date(2026, 11, 3), 91.0)])
        assert sc.evaluate(record(), None, d, LATER) == {}

    def test_unsorted_daily_bars(self):
        days = weekdays(MON, 2)
        d = daily([(days[1], 105.0), (days[0], 102.0)])
        out = sc.evaluate(record(), None, d, LATER)
        assert out["eod"] == 2.0 and out["d1"] == 5.0

    def test_first_touch_target_stop_and_neither(self):
        r = record(stop=99.0, target=102.0)
        up = five_min(MON, [100.0] * 20, highs=[100.5] * 12 + [102.1] + [100.5] * 7,
                      lows=[99.5] * 20)
        assert sc.evaluate(r, up, None, LATER)["first_touch"] == "target"
        down = five_min(MON, [100.0] * 20, highs=[100.5] * 20,
                        lows=[99.5] * 10 + [98.9] + [99.5] * 9)
        assert sc.evaluate(r, down, None, LATER)["first_touch"] == "stop"
        flat = five_min(MON, [100.0] * 20, highs=[100.5] * 20, lows=[99.5] * 20)
        assert sc.evaluate(r, flat, None, LATER)["first_touch"] == "neither"

    def test_first_touch_ignores_bars_before_the_alert(self):
        r = record(stop=99.0, target=102.0)
        early = five_min(MON, [100.0] * 20, highs=[103.0] * 3 + [100.5] * 17, lows=[99.5] * 20)
        assert sc.evaluate(r, early, None, LATER)["first_touch"] == "neither"

    def test_first_touch_both_in_one_bar_counts_as_stop(self):
        r = record(stop=99.0, target=102.0)
        both = five_min(MON, [100.0] * 20, highs=[100.5] * 12 + [102.5] + [100.5] * 7,
                        lows=[99.5] * 12 + [98.5] + [99.5] * 7)
        assert sc.evaluate(r, both, None, LATER)["first_touch"] == "stop"

    def test_first_touch_for_a_short(self):
        r = record(direction="down", stop=101.0, target=98.0)
        bars = five_min(MON, [100.0] * 20, highs=[100.5] * 20,
                        lows=[99.5] * 10 + [97.9] + [99.5] * 9)
        assert sc.evaluate(r, bars, None, LATER)["first_touch"] == "target"

    def test_first_touch_waits_for_the_day_to_end(self):
        r = record(stop=99.0, target=102.0)
        flat = five_min(MON, [100.0] * 20, highs=[100.5] * 20, lows=[99.5] * 20)
        assert "first_touch" not in sc.evaluate(r, flat, None, today=MON)


# ------------------------------------------------------------------ refresh

class TestRefresh:
    def _feeds(self, monkeypatch, daily_map, five_map=None, fail=False):
        calls = []
        def multi(symbols, days=200, timeframe=None):
            calls.append((sorted(symbols), "5m" if timeframe is not None else "1d"))
            if fail:
                raise RuntimeError("alpaca down")
            src = five_map if timeframe is not None else daily_map
            return {s: src[s] for s in symbols if s in (src or {})}
        monkeypatch.setattr(sc.client, "get_multi_bars", multi)
        return calls

    def test_fills_outcomes_and_marks_final(self, monkeypatch):
        days = weekdays(MON, 7)
        sc.log_alerts([alert()], now=MON_10)
        self._feeds(monkeypatch, {"NVDA": daily([(d, 100.0 + i) for i, d in enumerate(days)])})
        now = datetime(2026, 11, 20, 12, 0, tzinfo=ET)
        assert sc.refresh_outcomes(now=now) == 1
        r = sc._load()[0]
        assert r["outcome"] == {"eod": 0.0, "d1": 1.0, "d5": 5.0} and r["final"] is True
        assert sc.refresh_outcomes(now=now) == 0          # nothing pending any more

    def test_recent_alerts_fetch_intraday_bars_and_old_ones_do_not(self, monkeypatch):
        sc.log_alerts([alert(symbol="NEW")], now=datetime(2026, 11, 19, 10, 0, tzinfo=ET))
        sc.log_alerts([alert(symbol="OLD")], now=datetime(2026, 11, 10, 10, 0, tzinfo=ET))
        calls = self._feeds(monkeypatch, {})
        sc.refresh_outcomes(now=datetime(2026, 11, 20, 12, 0, tzinfo=ET))
        assert (["NEW", "OLD"], "1d") in calls and (["NEW"], "5m") in calls

    def test_very_old_pending_record_is_closed_out(self, monkeypatch):
        sc.log_alerts([alert()], now=datetime.now(tz=ET) - timedelta(days=20))
        self._feeds(monkeypatch, {})
        assert sc.refresh_outcomes(now=datetime.now(tz=ET)) == 1
        assert sc._load()[0]["final"] is True

    def test_price_failure_changes_nothing(self, monkeypatch):
        sc.log_alerts([alert()], now=MON_10)
        self._feeds(monkeypatch, {}, fail=True)
        assert sc.refresh_outcomes(now=datetime(2026, 11, 20, tzinfo=ET)) == 0
        assert sc._load()[0]["outcome"] == {}

    def test_throttled_without_an_explicit_time(self, monkeypatch):
        sc.log_alerts([alert()], now=datetime.now(tz=ET))
        calls = self._feeds(monkeypatch, {})
        sc.refresh_outcomes()
        n = len(calls)
        sc.refresh_outcomes()
        assert len(calls) == n

    def test_alert_logged_during_a_refresh_is_not_lost(self, monkeypatch):
        days = weekdays(MON, 7)
        sc.log_alerts([alert()], now=MON_10)
        def multi(symbols, days_=200, timeframe=None, **k):
            sc.log_alerts([alert(symbol="LATE")], now=MON_10)       # arrives mid-refresh
            return {"NVDA": daily([(d, 100.0 + i) for i, d in enumerate(days)])}
        monkeypatch.setattr(sc.client, "get_multi_bars", lambda symbols, days=200, timeframe=None: multi(symbols))
        sc.refresh_outcomes(now=datetime(2026, 11, 20, tzinfo=ET))
        by = {r["symbol"]: r for r in sc._load()}
        assert set(by) == {"NVDA", "LATE"} and by["NVDA"]["final"] is True


# ------------------------------------------------------------------ summary

class TestSummary:
    def test_win_rate_and_average_per_kind_and_direction(self):
        recs = [
            record(id="1", outcome={"m15": 1.0, "eod": 2.0, "first_touch": "target"}),
            record(id="2", outcome={"m15": -1.0, "eod": 4.0, "first_touch": "stop"}),
            record(id="3", outcome={"m15": 3.0}),
            record(id="4", kind="exhaustion_top", direction="down", outcome={}),
        ]
        rows = sc.summarize(recs)
        hl = rows[0]
        assert (hl["kind"], hl["direction"], hl["alerts"]) == ("higher_low", "up", 3)
        assert hl["m15"] == {"n": 3, "win_pct": 67.0, "avg_pct": 1.0}
        assert hl["eod"] == {"n": 2, "win_pct": 100.0, "avg_pct": 3.0}
        assert hl["d5"] == {"n": 0, "win_pct": None, "avg_pct": None}
        assert hl["first_touch"] == {"n": 2, "target": 1, "stop": 1, "neither": 0}
        assert rows[1]["first_touch"] is None and rows[1]["m15"]["n"] == 0

    def test_zero_return_is_not_a_win(self):
        row = sc.summarize([record(outcome={"m15": 0.0})])[0]
        assert row["m15"]["win_pct"] == 0.0

    def test_empty(self):
        assert sc.summarize([]) == []

    def test_report_shape_and_window(self, monkeypatch):
        monkeypatch.setattr(sc.client, "get_multi_bars", lambda *a, **k: {})
        today = datetime.now(tz=ET)
        sc.log_alerts([alert(symbol="NEW")], now=today)
        sc.log_alerts([alert(symbol="OLDER")], now=today - timedelta(days=45))
        rep = sc.report(days=30)
        assert rep["total_alerts"] == 1 and [r["symbol"] for r in rep["recent"]] == ["NEW"]
        assert set(rep["horizons"]) == set(sc.HORIZONS)
        assert sc.report(days=90, refresh=False)["total_alerts"] == 2

    def test_route(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        monkeypatch.setattr(sc.client, "get_multi_bars", lambda *a, **k: {})
        app = FastAPI(); app.include_router(router)
        c = TestClient(app)
        assert set(c.get("/scorecard").json()) >= {"summary", "recent", "total_alerts"}
        assert c.get("/scorecard?days=0").status_code == 422
