"""Pre-market gap list (src/scanner/premarket.py). No network."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.scanner import premarket as pm

ET = ZoneInfo("America/New_York")
TUE = date(2026, 11, 10)
AT_915 = datetime(2026, 11, 10, 9, 15, tzinfo=ET)


def daily(close=100.0, volume=1_000_000, n=30, end=date(2026, 11, 9)):
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    idx = pd.DatetimeIndex([pd.Timestamp(x, tz="UTC") + pd.Timedelta(hours=5) for x in reversed(days)])
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close,
                         "volume": volume}, index=idx)


def bars(points, day=TUE):
    """points: [("HH:MM", close, volume)] in Eastern time, returned UTC-indexed."""
    idx, rows = [], []
    for hhmm, close, volume in points:
        h, m = map(int, hhmm.split(":"))
        idx.append(datetime(day.year, day.month, day.day, h, m, tzinfo=ET))
        rows.append((close, close * 1.001, close * 0.999, close, volume))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                      index=pd.DatetimeIndex(idx).tz_convert("UTC"))
    return df


def cal(symbol, time="time-pre-market", cap=5e9, surprise=10.0):
    return {"symbol": symbol, "time": time, "name": f"{symbol} Inc", "market_cap": cap,
            "eps_forecast": 0.1, "eps": 0.2, "surprise_pct": surprise}


@pytest.fixture
def world(monkeypatch):
    w = {"daily": {}, "intraday": {}, "cal": {}, "fail": set(), "requests": []}
    pm._cache.clear()

    def multi(symbols, days=200, timeframe=None):
        if "daily" in w["fail"]:
            raise RuntimeError("alpaca down")
        return {s: w["daily"][s] for s in symbols if s in w["daily"]}

    def intraday(symbols, minutes_back=120, timeframe_minutes=5):
        w["requests"].append((list(symbols), minutes_back))
        return {s: w["intraday"][s] for s in symbols if s in w["intraday"]}

    def nasdaq_day(day):
        if "calendar" in w["fail"]:
            raise RuntimeError("nasdaq down")
        return w["cal"].get(day.isoformat(), [])

    monkeypatch.setattr(pm.client, "get_multi_bars", multi)
    monkeypatch.setattr(pm.client, "get_intraday_multi_bars", intraday)
    monkeypatch.setattr(pm.ec, "nasdaq_day", nasdaq_day)
    w["measured_delay"] = None                     # freshness probe unavailable by default
    monkeypatch.setattr(pm, "_measured_delay", lambda now: w["measured_delay"])
    monkeypatch.setattr("src.data.news.latest_headlines",
                        lambda symbols, **k: {s: [{"headline": f"{s} headline"}]
                                              for s in symbols if s != "QUIET"})
    return w


def add(w, symbol, gap_close, pre_volume, prior=100.0, avg_volume=1_000_000, when="09:00"):
    w["daily"][symbol] = daily(prior, avg_volume)
    w["intraday"][symbol] = bars([("08:00", prior, 0), (when, gap_close, pre_volume)])


def run(w, symbols, now=AT_915, **kw):
    return pm.scan_premarket_gaps(symbols, now=now, **kw)


# -------------------------------------------------------------------- stats

class TestStats:
    def test_uses_only_todays_premarket_bars(self):
        b = pd.concat([
            bars([("08:00", 90.0, 999_999)], day=date(2026, 11, 9)),     # yesterday
            bars([("03:55", 91.0, 5), ("04:00", 101.0, 100), ("09:25", 104.0, 200),
                  ("09:30", 105.0, 5000), ("09:35", 106.0, 5000)]),
        ])
        s = pm.premarket_stats(b, TUE)
        assert s["pre_last"] == 104.0 and s["pre_volume"] == 300
        assert s["open_price"] == 105.0 and s["now_price"] == 106.0

    def test_before_the_open_now_is_the_premarket_price(self):
        s = pm.premarket_stats(bars([("08:00", 101.0, 100), ("09:00", 103.0, 100)]), TUE)
        assert s["open_price"] is None and s["now_price"] == 103.0

    def test_no_premarket_bars_today(self):
        assert pm.premarket_stats(bars([("09:30", 105.0, 5000)]), TUE) is None
        assert pm.premarket_stats(bars([("08:00", 101.0, 100)], day=date(2026, 11, 9)), TUE) is None
        assert pm.premarket_stats(pd.DataFrame(), TUE) is None
        assert pm.premarket_stats(None, TUE) is None

    def test_unsorted_and_naive_input(self):
        b = bars([("09:00", 103.0, 100), ("08:00", 101.0, 100)])
        b.index = b.index.tz_localize(None)                              # naive UTC
        assert pm.premarket_stats(b, TUE)["pre_last"] == 103.0


# --------------------------------------------------------------------- scan

class TestScan:
    def test_gap_on_real_volume_is_listed_with_its_headline(self, world):
        add(world, "RIOT", 103.85, 135_000, avg_volume=26_000_000)
        r = run(world, ["RIOT"])
        g = r["gaps"][0]
        assert (g["symbol"], g["direction"], g["gap_pct"]) == ("RIOT", "up", 3.85)
        assert g["prior_close"] == 100.0 and g["pre_volume"] == 135_000
        assert g["day_share_pct"] == 0.52 and g["headline"] == "RIOT headline"
        assert r["phase"] == "premarket" and r["data_ok"] is True

    def test_gap_down(self, world):
        add(world, "APPS", 76.9, 100_000)
        g = run(world, ["APPS"])["gaps"][0]
        assert g["direction"] == "down" and g["gap_pct"] == -23.1

    def test_small_gap_is_not_listed(self, world):
        add(world, "FLAT", 101.5, 500_000)
        assert run(world, ["FLAT"])["gaps"] == []

    def test_gap_on_a_few_shares_is_noise(self, world):
        add(world, "THIN", 120.0, 900, avg_volume=1_000_000)            # 0.09% of a day
        add(world, "ODD", 120.0, 3_000, avg_volume=100_000)             # 3% of a day, 3k shares
        assert run(world, ["THIN", "ODD"])["gaps"] == []

    def test_big_gap_in_a_quiet_stock_survives_on_relative_volume(self, world):
        # 14.6k shares is small in absolute terms but 1% of this stock's day
        add(world, "AAON", 120.9, 14_600, avg_volume=1_360_000)
        assert [g["symbol"] for g in run(world, ["AAON"])["gaps"]] == ["AAON"]

    def test_sorted_by_size_of_gap_either_direction(self, world):
        add(world, "A", 103.0, 100_000); add(world, "B", 90.0, 100_000); add(world, "C", 106.0, 100_000)
        assert [g["symbol"] for g in run(world, ["A", "B", "C"])["gaps"]] == ["B", "C", "A"]

    def test_reporters_join_the_universe_and_are_marked(self, world):
        world["cal"]["2026-11-10"] = [cal("EARN"), cal("LATER", time="time-after-hours"),
                                      cal("TINY", cap=2e8), cal("PBR.A")]
        world["cal"]["2026-11-09"] = [cal("LAST", time="time-after-hours"),
                                      cal("OLDAM", time="time-pre-market")]
        for s in ("EARN", "LATER", "TINY", "LAST", "OLDAM"):
            add(world, s, 110.0, 200_000)
        r = run(world, ["SPY"])
        listed = {g["symbol"]: g for g in r["gaps"]}
        # this morning's and last night's reporters only, $1B+, plain symbols
        assert set(listed) == {"EARN", "LAST"}
        assert listed["EARN"]["reported"] is True and listed["EARN"]["surprise_pct"] == 10.0
        assert r["reporters"] == 2

    def test_after_the_open_shows_whether_the_gap_held(self, world):
        world["daily"]["FADE"] = daily(100.0)
        world["intraday"]["FADE"] = bars([("09:00", 108.0, 200_000), ("09:30", 107.0, 9_000),
                                          ("10:00", 102.0, 9_000)])
        r = run(world, ["FADE"], now=datetime(2026, 11, 10, 10, 5, tzinfo=ET))
        g = r["gaps"][0]
        assert r["phase"] == "open" and g["gap_pct"] == 8.0
        assert g["open_price"] == 107.0 and g["now_pct"] == 2.0
        assert any("has opened" in n for n in r["notes"])

    def test_delay_is_reported_when_data_is_behind(self, world):
        add(world, "RIOT", 104.0, 200_000, when="08:55")               # newest bar 20 min old
        r = run(world, ["RIOT"])
        assert r["delay_minutes"] == 15 and r["data_as_of"].startswith("2026-11-10T08:55")
        assert any("15 minutes behind" in n for n in r["notes"])

    def test_delay_matches_the_shared_measurement_when_available(self, world):
        add(world, "RIOT", 104.0, 200_000, when="09:00")               # bars alone would say 10
        world["measured_delay"] = 14
        r = run(world, ["RIOT"])
        assert r["delay_minutes"] == 14
        assert any("about 14 minutes behind" in n for n in r["notes"])

    def test_measured_real_time_data_shows_no_note(self, world):
        add(world, "RIOT", 104.0, 200_000, when="08:55")
        world["measured_delay"] = 0
        r = run(world, ["RIOT"])
        assert r["delay_minutes"] == 0 and not any("behind" in n for n in r["notes"])

    def test_no_delay_note_when_data_is_current(self, world):
        add(world, "RIOT", 104.0, 200_000, when="09:10")
        assert not any("behind" in n for n in run(world, ["RIOT"])["notes"])

    def test_crypto_malformed_and_unknown_symbols(self, world):
        add(world, "GOOD", 105.0, 100_000)
        r = run(world, ["BTC/USD", "BRK-B", "GOOD", "NODAT", "TOOLONGX"])
        assert [g["symbol"] for g in r["gaps"]] == ["GOOD"]
        assert world["requests"][0][0] == ["GOOD", "NODAT"]     # only well-formed tickers are requested

    def test_lookback_reaches_back_to_four_am(self, world):
        add(world, "GOOD", 105.0, 100_000)
        run(world, ["GOOD"])
        assert world["requests"][0][1] >= 315                           # 04:00 -> 09:15

    def test_no_headline_is_blank_not_missing(self, world):
        add(world, "QUIET", 105.0, 100_000)
        assert run(world, ["QUIET"])["gaps"][0]["headline"] == ""

    def test_zero_or_missing_history_is_skipped(self, world):
        world["daily"]["ZERO"] = daily(0.0)
        world["intraday"]["ZERO"] = bars([("09:00", 5.0, 100_000)])
        world["daily"]["NEW"] = daily(100.0, n=2)
        world["intraday"]["NEW"] = bars([("09:00", 120.0, 100_000)])
        assert run(world, ["ZERO", "NEW"])["gaps"] == []


class TestSessionsAndFailures:
    def test_weekend(self, world):
        r = run(world, ["RIOT"], now=datetime(2026, 11, 14, 9, 0, tzinfo=ET))
        assert r["gaps"] == [] and r["phase"] == "closed" and world["requests"] == []

    def test_before_four_am(self, world):
        r = run(world, ["RIOT"], now=datetime(2026, 11, 10, 3, 30, tzinfo=ET))
        assert r["phase"] == "closed" and "4:00 AM" in r["notes"][0]

    def test_price_data_failure(self, world):
        world["fail"].add("daily")
        r = run(world, ["RIOT"])
        assert r["data_ok"] is False and r["gaps"] == []

    def test_calendar_failure_still_scans_the_watch_universe(self, world):
        world["fail"].add("calendar")
        add(world, "RIOT", 104.0, 200_000, avg_volume=26_000_000)
        r = run(world, ["RIOT"])
        assert [g["symbol"] for g in r["gaps"]] == ["RIOT"] and r["reporters"] == 0

    def test_scorecard_alerts(self, world):
        add(world, "UP", 105.0, 100_000); add(world, "DOWN", 95.0, 100_000)
        alerts = pm.scorecard_alerts(run(world, ["UP", "DOWN"]))
        assert {(a["symbol"], a["kind"], a["direction"]) for a in alerts} == \
            {("UP", "premarket_gap", "up"), ("DOWN", "premarket_gap", "down")}
        assert all(a["price"] > 0 and a["time"] for a in alerts)
        assert pm.scorecard_alerts({"gaps": []}) == [] and pm.scorecard_alerts({}) == []

    def test_route(self, world, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        app = FastAPI(); app.include_router(router)
        c = TestClient(app)
        body = c.get("/scanner/premarket-gaps").json()
        assert set(body) >= {"gaps", "phase", "notes", "data_ok"}
        assert c.get("/scanner/premarket-gaps?min_gap_pct=0").status_code == 422
