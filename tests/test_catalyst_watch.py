"""Tests for the catalyst watch scan (src/scanner/catalyst_watch.py). No network."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.scanner import catalyst_watch as cw

ET = ZoneInfo("America/New_York")
TUE = datetime(2026, 11, 10, 11, 0, tzinfo=ET)        # Tuesday


def bars(closes, volumes=None, end=date(2026, 11, 9)):
    """Daily bars ending on `end` (weekdays only), oldest first."""
    n = len(closes)
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    idx = pd.DatetimeIndex([pd.Timestamp(x, tz="UTC") for x in reversed(days)])
    vols = volumes or [1_000_000] * n
    return pd.DataFrame({"open": closes, "high": [c * 1.01 for c in closes],
                         "low": [c * 0.99 for c in closes], "close": closes,
                         "volume": vols}, index=idx)


def cal(symbol, **kw):
    row = {"symbol": symbol, "time": "time-after-hours", "name": f"{symbol} Inc",
           "market_cap": 5e9, "eps_forecast": 0.1, "eps": None, "surprise_pct": None}
    row.update(kw)
    return row


def si(dtc, chg=0.0):
    return {"shares_short": 1_000_000, "prev_shares_short": 900_000, "avg_daily_volume": 100_000,
            "days_to_cover": dtc, "change_pct": chg, "settlement_date": "2026-10-15"}


@pytest.fixture
def world(monkeypatch):
    """Fake sources. Fill w['cal'][iso date], w['si'], w['bars'] per test."""
    w = {"cal": {}, "si": {}, "bars": {}, "assets": None, "bar_calls": [], "fail": set(),
         "history": {}, "history_calls": []}
    cw._cache.clear()

    def earnings_history(symbol):
        w["history_calls"].append(symbol)
        return w["history"].get(symbol)          # None = unavailable

    def nasdaq_day(day):
        if "nasdaq" in w["fail"]:
            return None
        return w["cal"].get(day.isoformat(), [])

    def multi_bars(symbols, days=200):
        w["bar_calls"].append((list(symbols), days))
        if "bars" in w["fail"]:
            raise RuntimeError("alpaca down")
        return {s: w["bars"][s] for s in symbols if s in w["bars"]}

    def assets():
        if w["assets"] is None:
            raise ValueError("10 validation errors for list[Asset]\nmore\nlines")
        return [{"symbol": s} for s in w["assets"]]

    def short_interest():
        if "finra" in w["fail"]:
            raise RuntimeError("finra down")
        return w["si"]

    import src.data.finra_client as finra
    monkeypatch.setattr(cw.ec, "nasdaq_day", nasdaq_day)
    monkeypatch.setattr(cw.ec, "earnings_history", earnings_history)
    monkeypatch.setattr(cw.client, "get_multi_bars", multi_bars)
    monkeypatch.setattr(cw.client, "get_tradeable_assets", assets)
    monkeypatch.setattr(finra, "get_short_interest", short_interest)
    return w


FLAT = [20.0] * 70


def run(**kw):
    return cw.scan_catalyst_watch(now=TUE, **kw)


# ----------------------------------------------------------------- helpers

class TestHelpers:
    def test_trading_days_forward_includes_today_and_skips_weekends(self):
        fri = date(2026, 11, 13)
        assert cw._trading_days(fri, 3, 1) == [date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 17)]

    def test_trading_days_backward_excludes_today(self):
        mon = date(2026, 11, 9)
        assert cw._trading_days(mon, 2, -1) == [date(2026, 11, 6), date(2026, 11, 5)]

    def test_trading_days_from_a_weekend(self):
        assert cw._trading_days(date(2026, 11, 14), 1, 1) == [date(2026, 11, 16)]

    def test_price_stats(self):
        closes = [30.0] * 40 + [10.0] * 20 + [12.0] * 9 + [15.0]
        s = cw.price_stats(bars(closes, [1_000_000] * 69 + [3_000_000]))
        assert s["price"] == 15.0 and s["last_day_pct"] == 25.0 and s["last_day_rvol"] == 3.0
        assert s["chg_5d"] == 25.0
        assert 0 < s["range_pos"] < 40                  # near the low of a 9.9-30.3 range

    def test_price_stats_needs_history_and_survives_bad_input(self):
        assert cw.price_stats(None) is None
        assert cw.price_stats(bars([10.0] * 10)) is None
        assert cw.price_stats(pd.DataFrame()) is None
        assert cw.price_stats(bars([0.0] * 30)) is None

    def test_price_stats_sorts_reversed_input(self):
        df = bars([10.0] * 29 + [20.0])
        assert cw.price_stats(df.iloc[::-1])["price"] == 20.0

    def test_flat_range_is_mid(self):
        df = bars([10.0] * 30)
        df["high"] = df["low"] = 10.0
        assert cw.price_stats(df)["range_pos"] == 50.0

    def test_coiled_score_bounds_and_ingredients(self):
        assert cw.coiled_score(10, 20, 0, 0) == 100.0
        assert cw.coiled_score(0, -5, 100, 9) == 0.0
        assert cw.coiled_score(50, 500, -10, -3) == 100.0      # clamped
        assert cw.coiled_score(5, 0, 100, 9) == 17.5           # only days to cover
        base = cw.coiled_score(5, 0, 50, 3)
        assert cw.coiled_score(5, 10, 50, 3) > base            # shorts building
        assert cw.coiled_score(5, 0, 10, 3) > base             # nearer the low
        assert cw.coiled_score(5, 0, 50, 0) > base             # event sooner

    def test_best_reaction_picks_the_strongest_day_in_the_window(self):
        closes = [10.0] * 66 + [11.8, 13.0, 12.5, 14.0]
        vols = [1_000_000] * 66 + [2_200_000, 4_500_000, 2_000_000, 2_500_000]
        r = cw.best_reaction(bars(closes, vols), since=date(2026, 11, 3))
        assert r["reaction_date"] == "2026-11-04" and r["reaction_pct"] == 18.0
        assert r["reaction_rvol"] == 2.2
        assert r["since_reaction_pct"] == pytest.approx((14.0 / 11.8 - 1) * 100, abs=0.01)

    def test_best_reaction_ignores_days_before_the_window(self):
        closes = [10.0] * 60 + [20.0] + [20.0] * 9
        r = cw.best_reaction(bars(closes), since=date(2026, 11, 5))
        assert r["reaction_pct"] == 0.0

    def test_best_reaction_bad_input(self):
        assert cw.best_reaction(None, date(2026, 11, 3)) is None
        assert cw.best_reaction(bars([10.0] * 5), date(2026, 11, 3)) is None

    def test_usable_symbols(self):
        assert cw._usable("RIOT", None) and not cw._usable("PBR.A", None)
        assert not cw._usable("BRK-B", None) and not cw._usable("TOOLONG", None)
        assert cw._usable("RIOT", {"RIOT"}) and not cw._usable("RIOT", {"MARA"})


# ---------------------------------------------------------------- upcoming

class TestUpcoming:
    def test_needs_earnings_soon_and_trapped_shorts(self, world):
        world["cal"]["2026-11-11"] = [cal("COIL"), cal("CALM"), cal("NOSI")]
        world["cal"]["2026-11-20"] = [cal("LATE")]            # beyond 5 sessions
        world["si"] = {"COIL": si(8.0, 12.0), "CALM": si(1.0), "LATE": si(9.0)}
        world["bars"] = {s: bars(FLAT) for s in ("COIL", "CALM", "NOSI", "LATE")}
        r = run()
        assert [x["symbol"] for x in r["upcoming"]] == ["COIL"]
        row = r["upcoming"][0]
        assert (row["earnings_date"], row["days_until"], row["session"]) == ("2026-11-11", 1, "amc")
        assert row["days_to_cover"] == 8.0 and row["si_change_pct"] == 12.0
        assert r["data_ok"] is True and r["short_interest_date"] == "2026-10-15"

    def test_only_prices_symbols_that_passed_the_short_interest_gate(self, world):
        world["cal"]["2026-11-10"] = [cal("COIL"), cal("CALM")]
        world["si"] = {"COIL": si(8.0), "CALM": si(1.0)}
        world["bars"] = {"COIL": bars(FLAT), "CALM": bars(FLAT)}
        run()
        assert world["bar_calls"][0][0] == ["COIL", "SPY"]      # SPY is the market yardstick

    def test_ranked_by_score(self, world):
        world["cal"]["2026-11-10"] = [cal("LOW"), cal("HIGH")]
        world["si"] = {"LOW": si(3.0), "HIGH": si(10.0, 20.0)}
        world["bars"] = {"LOW": bars(FLAT), "HIGH": bars(FLAT)}
        r = run()
        assert [x["symbol"] for x in r["upcoming"]] == ["HIGH", "LOW"]
        assert r["upcoming"][0]["score"] > r["upcoming"][1]["score"]

    def test_filters_price_volume_market_cap_and_odd_symbols(self, world):
        world["cal"]["2026-11-10"] = [
            cal("PENNY"), cal("THIN"), cal("TINY", market_cap=1e8), cal("PBR.A"),
            cal("NOCAP", market_cap=None), cal("NOBAR"),
        ]
        world["si"] = {s: si(9.0) for s in ("PENNY", "THIN", "TINY", "PBR.A", "NOCAP", "NOBAR")}
        world["bars"] = {"PENNY": bars([2.0] * 70), "THIN": bars(FLAT, [10_000] * 70),
                         "TINY": bars(FLAT), "NOCAP": bars(FLAT)}
        assert [x["symbol"] for x in run()["upcoming"]] == ["NOCAP"]   # unknown cap is kept

    def test_asset_list_restricts_symbols_when_available(self, world):
        world["assets"] = {"REAL"}
        world["cal"]["2026-11-10"] = [cal("REAL"), cal("GHOST")]
        world["si"] = {"REAL": si(9.0), "GHOST": si(9.0)}
        world["bars"] = {"REAL": bars(FLAT), "GHOST": bars(FLAT)}
        assert [x["symbol"] for x in run()["upcoming"]] == ["REAL"]

    def test_early_move_flag(self, world):
        world["cal"]["2026-11-11"] = [cal("EARLY"), cal("QUIET")]
        world["si"] = {"EARLY": si(5.0), "QUIET": si(5.0)}
        world["bars"] = {"EARLY": bars([20.0] * 69 + [23.0], [1_000_000] * 69 + [2_500_000]),
                         "QUIET": bars([20.0] * 69 + [23.0])}          # same move, no volume
        flags = {x["symbol"]: x["early_move"] for x in run()["upcoming"]}
        assert flags == {"EARLY": True, "QUIET": False}

    def test_symbol_on_two_dates_uses_the_nearest(self, world):
        world["cal"]["2026-11-10"] = [cal("DUP")]
        world["cal"]["2026-11-12"] = [cal("DUP")]
        world["si"] = {"DUP": si(9.0)}
        world["bars"] = {"DUP": bars(FLAT)}
        assert run()["upcoming"][0]["earnings_date"] == "2026-11-10"


# ---------------------------------------------------------------- reacting

RIOT_CLOSES = [13.0] * 64 + [12.81, 11.84, 14.02, 15.37, 14.76, 16.71, 17.66]
RIOT_VOLS = [18_000_000] * 64 + [25_700_000, 17_700_000, 40_800_000, 83_800_000,
                                 49_200_000, 45_100_000, 28_900_000]


class TestReacting:
    def test_riot_week_is_found(self, world):
        world["cal"]["2026-11-04"] = [cal("RIOT", time="time-not-supplied", eps=0.01,
                                          eps_forecast=-0.34, surprise_pct=102.94)]
        world["si"] = {"RIOT": si(3.03, 11.19)}
        world["bars"] = {"RIOT": bars(RIOT_CLOSES, RIOT_VOLS)}
        r = run()["reacting"]
        assert len(r) == 1
        x = r[0]
        assert x["reaction_date"] == "2026-11-03" and x["reaction_pct"] == 18.41
        assert x["reaction_rvol"] >= 2.0 and x["since_reaction_pct"] == 25.96
        assert (x["surprise_pct"], x["eps"], x["session"]) == (102.94, 0.01, "")
        assert x["days_to_cover"] == 3.03 and x["price"] == 17.66

    def test_needs_both_a_big_day_and_heavy_volume(self, world):
        world["cal"]["2026-11-05"] = [cal("SMALL"), cal("NOVOL"), cal("DOWN")]
        world["bars"] = {
            "SMALL": bars([20.0] * 68 + [20.6, 20.6], [1_000_000] * 68 + [5_000_000, 1_000_000]),
            "NOVOL": bars([20.0] * 68 + [23.0, 23.0]),
            "DOWN": bars([20.0] * 68 + [16.0, 16.0], [1_000_000] * 68 + [5_000_000, 1_000_000]),
        }
        assert run()["reacting"] == []

    def test_works_without_short_interest(self, world):
        world["fail"].add("finra")
        world["cal"]["2026-11-05"] = [cal("POP")]
        world["bars"] = {"POP": bars([20.0] * 68 + [24.0, 24.5],
                                     [1_000_000] * 68 + [4_000_000, 1_500_000])}
        r = run()
        assert [x["symbol"] for x in r["reacting"]] == ["POP"]
        assert r["reacting"][0]["days_to_cover"] == 0.0
        assert r["upcoming"] == [] and r["data_ok"] is False
        assert any("short interest" in n for n in r["notes"])

    def test_old_reports_are_out_of_the_window(self, world):
        world["cal"]["2026-10-20"] = [cal("OLD")]
        world["bars"] = {"OLD": bars([20.0] * 68 + [24.0, 24.0],
                                     [1_000_000] * 68 + [4_000_000, 1_000_000])}
        assert run()["reacting"] == []

    def test_largest_companies_are_priced_first_under_the_cap(self, world, monkeypatch):
        monkeypatch.setattr(cw, "_MAX_REACTING", 2)
        world["cal"]["2026-11-05"] = [cal("SML", market_cap=4e8), cal("BIG", market_cap=9e10),
                                      cal("MID", market_cap=5e9)]
        run()
        assert world["bar_calls"][-1][0] == ["BIG", "MID"]


# ---------------------------------------------------------------- failures

class TestFailures:
    def test_calendar_down(self, world):
        world["fail"].add("nasdaq")
        r = run()
        assert r["upcoming"] == [] and r["reacting"] == [] and r["data_ok"] is False
        assert len(r["notes"]) >= 1 and world["bar_calls"] == []

    def test_price_data_down(self, world):
        world["fail"].add("bars")
        world["cal"]["2026-11-10"] = [cal("COIL")]
        world["si"] = {"COIL": si(9.0)}
        r = run()
        assert r["upcoming"] == [] and "Price data unavailable." in r["notes"]

    def test_nothing_reporting(self, world):
        world["si"] = {"ANY": si(1.0)}          # FINRA answered; nobody is on the calendar
        r = run()
        assert r["upcoming"] == [] and r["reacting"] == [] and r["data_ok"] is True

    def test_good_result_is_cached_and_a_failed_one_is_not(self, world, monkeypatch):
        world["cal"][datetime.now(tz=ET).date().isoformat()] = []
        world["si"] = {"ANY": si(1.0)}
        cw.scan_catalyst_watch()
        assert len(cw._cache) == 1
        cw._cache.clear()
        world["fail"].add("nasdaq")
        cw.scan_catalyst_watch()
        assert cw._cache == {}

    def test_route(self, world):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        app = FastAPI(); app.include_router(router)
        c = TestClient(app)
        body = c.get("/scanner/catalyst-watch").json()
        assert set(body) >= {"upcoming", "reacting", "data_ok", "notes", "short_interest_date"}
        assert c.get("/scanner/catalyst-watch?days_ahead=0").status_code == 422

    def test_empty_short_interest_table_counts_as_unavailable(self, world):
        r = run()                                  # FINRA returned nothing at all
        assert r["data_ok"] is False and any("short interest" in n for n in r["notes"])


# ------------------------------------------------- 52-week range and scoring

class TestYearRange:
    def test_three_month_high_but_near_the_bottom_of_its_year(self):
        # AECOM-like: 130 a year ago, sold off to 58, now 70 at its 3-month high
        closes = [130.0] * 120 + [100.0] * 60 + [62.0] * 60 + [58.0] * 5 + [64.0, 66.0, 68.0, 70.0]
        s = cw.price_stats(bars(closes))
        assert s["range_pos"] > 90 and s["range_pos_52w"] < 20
        assert s["low_52w"] < 58.0 and s["high_52w"] > 130.0

    def test_short_history_has_no_year_range(self):
        s = cw.price_stats(bars([20.0] * 70))
        assert s["range_pos_52w"] is None and s["low_52w"] is None

    def test_beaten_down_on_the_year_raises_the_score(self):
        base = cw.coiled_score(5, 0, 100, 3)                      # 3-month high, no year view
        assert cw.coiled_score(5, 0, 100, 3, range_pos_52w=17) > base
        assert cw.coiled_score(5, 0, 100, 3, range_pos_52w=100) == base
        assert cw.coiled_score(10, 20, 0, 0, range_pos_52w=0) == 100.0
        assert cw.coiled_score(5, 0, 100, 3, range_pos_52w=250) == base     # clamped


# ------------------------------------------------------ past earnings reactions

def acm_bars():
    """Daily closes around four after-close reports, AECOM's real pattern."""
    days = {
        date(2025, 11, 17): 126.6, date(2025, 11, 18): 125.1, date(2025, 11, 19): 111.2,
        date(2026, 2, 6): 98.0, date(2026, 2, 9): 99.7, date(2026, 2, 10): 100.8,
        date(2026, 2, 11): 97.9, date(2026, 2, 12): 85.8,
        date(2026, 5, 8): 79.8, date(2026, 5, 11): 78.7, date(2026, 5, 12): 69.3,
        date(2026, 8, 7): 75.5, date(2026, 8, 10): 73.0, date(2026, 8, 11): 66.8,
        date(2026, 8, 12): 60.8,
    }
    idx = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=5) for d in days])
    c = list(days.values())
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1}, index=idx)


ACM_HISTORY = [{"date": "2026-08-10", "surprise_pct": -133.56},
               {"date": "2026-05-11", "surprise_pct": 0.63},
               {"date": "2026-02-09", "surprise_pct": -8.51},
               {"date": "2025-11-18", "surprise_pct": 1.49}]


class TestPastReactions:
    def test_after_close_reporter_uses_the_next_session(self):
        r = cw.past_reactions(acm_bars(), ACM_HISTORY, "amc")
        assert [(x["date"], x["reaction_date"], x["move_pct"]) for x in r] == [
            ("2026-08-10", "2026-08-11", -8.49), ("2026-05-11", "2026-05-12", -11.94),
            ("2026-02-09", "2026-02-10", 1.1), ("2025-11-18", "2025-11-19", -11.11)]
        assert r[0]["surprise_pct"] == -133.56

    def test_a_later_selloff_is_not_counted_as_the_reaction(self):
        feb = cw.past_reactions(acm_bars(), ACM_HISTORY, "amc")[2]
        assert feb["move_pct"] == 1.1          # the -12% on Feb 12 came three days later

    def test_before_open_reporter_uses_the_same_session(self):
        r = cw.past_reactions(acm_bars(), ACM_HISTORY[:1], "bmo")
        assert (r[0]["reaction_date"], r[0]["move_pct"]) == ("2026-08-10", -3.31)

    def test_unknown_timing_takes_the_larger_move(self):
        r = cw.past_reactions(acm_bars(), ACM_HISTORY[:1], "")
        assert (r[0]["reaction_date"], r[0]["move_pct"]) == ("2026-08-11", -8.49)

    def test_unavailable_history_is_none_and_empty_history_is_empty(self):
        assert cw.past_reactions(acm_bars(), None, "amc") is None
        assert cw.past_reactions(acm_bars(), [], "amc") == []
        assert cw.past_reactions(None, ACM_HISTORY, "amc") is None

    def test_reports_outside_the_price_history_are_skipped(self):
        hist = [{"date": "2030-01-01"}, {"date": "2019-01-01"}, {"date": "2026-05-11"}]
        r = cw.past_reactions(acm_bars(), hist, "amc")
        # 2030 is past the data; 2019 predates it and must not be pinned to the first bar
        assert [x["date"] for x in r] == ["2026-05-11"]

    def test_report_just_before_the_history_starts_is_skipped(self):
        # first bar is 2025-11-17; a report a month earlier has no session of its own
        assert cw.past_reactions(acm_bars(), [{"date": "2025-10-15"}], "amc") == []

    def test_report_on_a_weekend_uses_the_next_session(self):
        r = cw.past_reactions(acm_bars(), [{"date": "2026-05-09"}], "bmo")     # Saturday
        assert r[0]["reaction_date"] == "2026-05-11"

    def test_limit_and_malformed_rows_and_unsorted_bars(self):
        hist = [{"date": "garbage"}, {}] + ACM_HISTORY
        assert len(cw.past_reactions(acm_bars(), hist, "amc", limit=2)) == 2
        assert cw.past_reactions(acm_bars().iloc[::-1], ACM_HISTORY, "amc")[0]["move_pct"] == -8.49


class TestScanEnrichment:
    def _setup(self, world, spy_last=100.0):
        world["cal"]["2026-11-16"] = [cal("ACM", name="AECOM")]
        world["si"] = {"ACM": si(4.37, 3.8)}
        world["bars"]["SPY"] = bars([100.0] * 69 + [spy_last])

    def test_move_explained_by_the_market_is_not_an_early_move(self, world):
        self._setup(world, spy_last=102.4)                       # market +2.4%
        world["bars"]["ACM"] = bars([66.74] * 69 + [70.21], [1_147_000] * 69 + [2_280_000])
        row = run()["upcoming"][0]
        assert row["last_day_pct"] == 5.2 and row["last_day_vs_market"] == 2.8
        assert row["early_move"] is False

    def test_move_well_beyond_the_market_is_an_early_move(self, world):
        self._setup(world, spy_last=102.4)
        world["bars"]["ACM"] = bars([66.74] * 69 + [72.5], [1_147_000] * 69 + [2_500_000])
        assert run()["upcoming"][0]["early_move"] is True

    def test_market_data_missing_falls_back_to_the_raw_move(self, world):
        world["cal"]["2026-11-16"] = [cal("ACM")]
        world["si"] = {"ACM": si(4.37)}
        world["bars"]["ACM"] = bars([66.74] * 69 + [70.21], [1_147_000] * 69 + [2_280_000])
        row = run()["upcoming"][0]
        assert row["last_day_vs_market"] == row["last_day_pct"] and row["early_move"] is True

    def test_past_reactions_and_typical_move_are_attached(self, world):
        self._setup(world)
        base = acm_bars()
        tail = bars([70.0] * 40)                                  # recent sessions for the stats
        world["bars"]["ACM"] = pd.concat([base, tail]).sort_index()
        world["history"]["ACM"] = ACM_HISTORY
        row = run()["upcoming"][0]
        assert [r["move_pct"] for r in row["past_reactions"]] == [-8.49, -11.94, 1.1, -11.11]
        assert row["typical_move_pct"] == 8.2

    def test_history_unavailable_leaves_reactions_unknown(self, world):
        self._setup(world)
        world["bars"]["ACM"] = bars([70.0] * 70)
        row = run()["upcoming"][0]
        assert row["past_reactions"] is None and row["typical_move_pct"] is None

    def test_history_lookups_are_capped(self, world, monkeypatch):
        monkeypatch.setattr(cw, "_MAX_HISTORY", 2)
        world["cal"]["2026-11-16"] = [cal(s) for s in ("AA", "BB", "CC", "DD")]
        world["si"] = {s: si(5.0 + i) for i, s in enumerate(("AA", "BB", "CC", "DD"))}
        for s in ("AA", "BB", "CC", "DD"):
            world["bars"][s] = bars([70.0] * 70)
        rows = run()["upcoming"]
        assert len(rows) == 4 and sorted(world["history_calls"]) == ["CC", "DD"]   # top two by score

    def test_spy_is_never_listed_as_a_candidate(self, world):
        self._setup(world)
        world["bars"]["ACM"] = bars([70.0] * 70)
        world["cal"]["2026-11-16"].append(cal("SPY"))
        world["si"]["SPY"] = si(9.0)
        assert {r["symbol"] for r in run()["upcoming"]} == {"ACM", "SPY"}   # only if it truly reports
