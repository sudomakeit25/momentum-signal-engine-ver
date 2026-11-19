"""The probability map's live record: tables saved after each session and
scored once their windows finish. Synthetic bars; no network, no Redis."""

import inspect
import json
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from src.data import client
from src.scanner import map_record as mr
from src.scanner import probability_map as pm

ET = ZoneInfo("America/New_York")
SYMS = ["CLSK", "RIOT", "NVDA"]
N = 700
I0 = 600                      # first evening recorded (index into the sessions)


def walk(n, sig, seed, price=20.0):
    rng = np.random.default_rng(seed)
    s = np.full(n, sig)
    gaps = rng.normal(0, 0.3, n) * s
    oc = rng.normal(0, math.sqrt(0.91), n) * s
    close = price * np.exp(np.cumsum(gaps + oc))
    prev = np.r_[price, close[:-1]]
    opn = prev * np.exp(gaps)
    hi = np.maximum(opn, close) * np.exp(np.abs(rng.normal(0, 0.4, n)) * s)
    lo = np.minimum(opn, close) * np.exp(-np.abs(rng.normal(0, 0.4, n)) * s)
    return pd.DataFrame({"open": opn, "high": hi, "low": lo, "close": close, "volume": 1e6},
                        index=pd.bdate_range("2024-01-01", periods=n, tz=ET))


BARS = {s: walk(N, 0.05, seed=i + 1) for i, s in enumerate(SYMS)}
BARS["SPY"] = walk(N, 0.01, seed=99, price=400.0)
DAYS = [t.date() for t in BARS["SPY"].index]


def evening(i, hh=17):
    d = DAYS[i]
    return datetime(d.year, d.month, d.day, hh, 0, tzinfo=ET)


@pytest.fixture
def market(monkeypatch):
    state = {"bars": {s: b.copy() for s, b in BARS.items()}, "calls": [], "fail": set()}

    def fake(symbols, days=200, **kw):
        state["calls"].append(tuple(symbols))
        if set(symbols) & state["fail"]:
            raise RuntimeError("alpaca down")
        return {s: state["bars"][s].copy() for s in symbols if s in state["bars"]}

    monkeypatch.setattr(client, "get_multi_bars", fake)
    return state


def run(i, hh=17, **kw):
    mr._done_for = None            # each call stands for a later loop pass
    mr._failed_at = 0.0
    return mr.run_daily(now=evening(i, hh), symbols=kw.pop("symbols", SYMS), **kw)


def score():
    return json.loads(mr._mem[mr.score_key()])


def snap(i):
    return json.loads(mr._mem[mr.snap_key(str(DAYS[i]))])


def recount(rec, d, i, h):
    """Brier sums for one saved table and one window, from the definitions."""
    c, hi, lo = (d[k].to_numpy(float) for k in ("close", "high", "low"))
    best, worst = max(hi[i + 1:i + h + 1]) / c[i] - 1, min(lo[i + 1:i + h + 1]) / c[i] - 1
    j = pm.HORIZONS.index(h)
    bm = bu = 0.0
    for r, lvl in enumerate([30, 20, 10, 5, -5, -10, -20, -30]):
        hit = float(best >= lvl / 100 - 1e-12) if lvl > 0 else float(worst <= lvl / 100 + 1e-12)
        bm += (rec["o"][r][j] / 1e4 - hit) ** 2
        bu += (rec["u"][r][j] / 1e4 - hit) ** 2
    return bm, bu


def cut(sym, i):
    return pm.clean_bars(BARS[sym]).iloc[: i + 1]


class TestSaving:
    def test_first_evening_saves_every_stock(self, market):
        out = run(I0)
        assert out.startswith(f"saved 3 stocks for {DAYS[I0]}")
        s = snap(I0)
        assert set(s["symbols"]) == set(SYMS) and s["version"] == pm.METHOD_VERSION
        sc = score()
        assert sc["open"] == {str(DAYS[I0]): list(mr.KEYS)} and sc["since"] == str(DAYS[I0])
        assert sc["snapshots"] == 1 and sc["symbols"] == {}

    def test_saved_table_is_what_the_panel_showed(self, market):
        run(I0)
        rec = snap(I0)["symbols"]["CLSK"]
        shown = pm.build(cut("CLSK", I0), check=False)
        assert rec["c"] == shown["last_close"]
        assert rec["o"] == [[round(x * 10000) for x in r["odds"]] for r in shown["rows"]]
        assert rec["u"] == [[round(x * 10000) for x in r["usual"]] for r in shown["rows"]]

    def test_later_bars_are_not_used(self, market):
        run(I0)
        before = snap(I0)["symbols"]["RIOT"]
        mr._mem.clear()
        market["bars"]["RIOT"].iloc[I0 + 1:, :4] *= 3                   # a wild future
        run(I0)
        assert snap(I0)["symbols"]["RIOT"] == before

    def test_twice_the_same_evening_does_nothing(self, market):
        run(I0)
        first = dict(mr._mem)
        assert run(I0) is None and mr._mem == first
        assert mr.run_daily(now=evening(I0)) is None                    # remembered in memory too

    def test_during_the_session_it_records_the_day_before(self, market):
        assert run(I0, hh=12).startswith(f"saved 3 stocks for {DAYS[I0 - 1]}")

    def test_a_stock_that_did_not_trade_that_day_is_left_out(self, market):
        market["bars"]["NVDA"] = market["bars"]["NVDA"].drop(market["bars"]["NVDA"].index[I0])
        run(I0)
        assert set(snap(I0)["symbols"]) == {"CLSK", "RIOT"}


class TestScoring:
    def test_next_evening_scores_one_session_and_the_10pct_close(self, market):
        run(I0)
        run(I0 + 1)
        sc = score()
        assert sc["open"][str(DAYS[I0])] == ["5", "10", "20"]
        assert sc["open"][str(DAYS[I0 + 1])] == list(mr.KEYS)
        assert sc["days"] == {"1": 1, "5": 0, "10": 0, "20": 0, "n": 1, "o": 1}
        for sym in SYMS:
            rec = snap(I0)["symbols"][sym]
            bm, bu = recount(rec, cut(sym, I0 + 1), I0, 1)
            st = sc["symbols"][sym]
            assert st["h"]["1"] == [8, pytest.approx(bm), pytest.approx(bu)]
            assert st["next"][0] == 2 and st["open"][0] == 2

    def test_four_weeks_of_evenings_score_every_window_once(self, market):
        kept = {}
        for i in range(I0, I0 + 26):
            run(i)
            kept[i] = snap(i)                     # without Redis, fully scored tables are pruned
        assert mr.snap_key(str(DAYS[I0])) not in mr._mem
        sc = score()
        # sessions saved I0..I0+25; the 20-session window has finished for I0..I0+5
        assert sc["days"] == {"1": 25, "5": 21, "10": 16, "20": 6, "n": 25, "o": 25}
        assert str(DAYS[I0]) not in sc["open"]
        for sym in SYMS:
            for h in pm.HORIZONS:
                bm = bu = 0.0
                for i in range(I0, I0 + 26 - h):
                    rec = kept[i]["symbols"][sym]
                    a, b = recount(rec, cut(sym, I0 + 25), i, h)
                    bm, bu = bm + a, bu + b
                cells, got_m, got_u = sc["symbols"][sym]["h"][str(h)]
                assert cells == 8 * (26 - h)
                assert got_m == pytest.approx(bm) and got_u == pytest.approx(bu)

    def test_the_10pct_close_and_open_odds_match_a_recount(self, market):
        for i in range(I0, I0 + 4):
            run(i)
        st = score()["symbols"]["CLSK"]
        bars = cut("CLSK", I0 + 3)
        c, o = bars["close"].to_numpy(float), bars["open"].to_numpy(float)
        bm = bu = bo = 0.0
        happened = 0
        for i in range(I0, I0 + 3):
            rec = snap(i)["symbols"]["CLSK"]
            move = c[i + 1] / c[i] - 1
            hits = [float(move >= 0.10 - 1e-12), float(move <= -0.10 + 1e-12)]
            happened += int(sum(hits))
            bm += sum((rec["b"][k] / 1e4 - hits[k]) ** 2 for k in (0, 1))
            bu += sum((rec["b"][k + 2] / 1e4 - hits[k]) ** 2 for k in (0, 1))
            oo = pm.open_odds_at(pm.prepare(bars.iloc[: i + 1]), i, float(o[i + 1]))
            bo += (oo["up"] - hits[0]) ** 2 + (oo["down"] - hits[1]) ** 2
        assert st["next"] == [6, pytest.approx(bm), pytest.approx(bu), happened]
        assert st["open"] == [6, pytest.approx(bo), pytest.approx(bu)]

    def test_missed_evenings_are_caught_up_but_not_filled_in(self, market):
        run(I0)
        run(I0 + 7)
        sc = score()
        assert sorted(sc["open"]) == [str(DAYS[I0]), str(DAYS[I0 + 7])]
        assert sc["open"][str(DAYS[I0])] == ["10", "20"]
        assert sc["days"] == {"1": 1, "5": 1, "10": 0, "20": 0, "n": 1, "o": 1}
        assert mr.snap_key(str(DAYS[I0 + 3])) not in mr._mem             # never saved, never invented

    def test_a_failed_run_writes_nothing_and_the_retry_scores_once(self, market, monkeypatch):
        monkeypatch.setattr(mr, "CHUNK", 2)                                # CLSK, RIOT | NVDA
        run(I0)
        before = dict(mr._mem)
        market["fail"] = {"NVDA"}
        with pytest.raises(RuntimeError):
            run(I0 + 1)
        assert mr._mem == before                                            # the first chunk was not kept
        market["fail"] = set()
        run(I0 + 1)
        failed_then_ok = score()["symbols"]
        mr._mem.clear()
        run(I0)
        run(I0 + 1)
        assert failed_then_ok == score()["symbols"]                         # same as a clean run

    def test_a_split_between_saving_and_scoring_changes_nothing(self, market):
        run(I0)
        run(I0 + 5)
        plain = score()["symbols"]
        mr._mem.clear()
        run(I0)
        market["bars"]["CLSK"].iloc[:, :4] *= 0.5                          # history re-adjusted later
        run(I0 + 5)
        assert score()["symbols"]["CLSK"] == plain["CLSK"]

    def test_a_new_method_version_is_scored_apart(self, market, monkeypatch):
        run(I0)
        monkeypatch.setattr(pm, "METHOD_VERSION", 2)
        run(I0 + 1)
        assert json.loads(mr._mem[mr.score_key(1)])["symbols"] == {}        # v1 untouched
        assert json.loads(mr._mem[mr.score_key(2)])["snapshots"] == 1


class TestWhen:
    @pytest.mark.parametrize("hh,mm,ok", [(9, 24, True), (9, 25, False), (10, 14, False), (10, 15, True),
                                          (13, 0, True), (16, 20, True), (23, 0, True), (3, 0, True)])
    def test_due_outside_the_opening_rush(self, hh, mm, ok):
        assert mr.due(datetime(2026, 11, 18, hh, mm, tzinfo=ET)) is ok

    def test_only_a_failure_delays_the_next_try(self, market, monkeypatch):
        mr.run_daily(now=evening(I0), symbols=SYMS)
        assert mr.due(evening(I0)) is True                      # a finished run does not hold it back
        market["fail"] = {"CLSK"}
        with pytest.raises(RuntimeError):
            run(I0 + 1)
        assert mr.due(evening(I0 + 1)) is False
        monkeypatch.setattr(mr, "_failed_at", mr._failed_at - mr.RETRY_EVERY)
        assert mr.due(evening(I0 + 1)) is True

    def test_needs_work_only_when_a_new_session_has_finished(self, market):
        assert mr.needs_work(evening(I0)) is True
        mr.run_daily(now=evening(I0), symbols=SYMS)
        assert mr.needs_work(evening(I0, hh=20)) is False
        assert mr.needs_work(evening(I0 + 1)) is True

    @pytest.mark.parametrize("hh,mm,last", [(16, 24, I0 - 1), (16, 26, I0)])
    def test_a_session_counts_as_finished_from_16_25(self, market, hh, mm, last):
        d = DAYS[I0]
        assert mr.sessions(datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET))[-1] == DAYS[last]


class TestStorage:
    class FakeRedis:
        def __init__(self, fail=False):
            self.data, self.ex, self.fail = {}, {}, fail

        def get(self, key):
            if self.fail:
                raise ConnectionError("upstash down")
            return self.data.get(key)

        def set(self, key, value, ex=None):
            self.data[key], self.ex[key] = value, ex

    def test_snapshots_expire_and_totals_do_not(self, market, monkeypatch):
        r = self.FakeRedis()
        monkeypatch.setattr(mr, "_redis", lambda: r)
        run(I0)
        assert r.ex[mr.snap_key(str(DAYS[I0]))] == mr.SNAP_TTL
        assert r.ex[mr.score_key()] is None and mr._mem == {}

    def test_a_redis_outage_stops_the_run_and_reads_say_so(self, market, monkeypatch):
        r = self.FakeRedis(fail=True)
        monkeypatch.setattr(mr, "_redis", lambda: r)
        with pytest.raises(ConnectionError):
            run(I0)
        assert r.data == {}
        assert mr.live_for("CLSK") is None
        assert mr.report() == {"ok": False, "note": "Could not read the record right now."}


class TestReading:
    def test_before_anything_is_saved(self):
        assert mr.live_for("CLSK") is None
        assert mr.report()["since"] is None

    def test_report_and_verdict_thresholds(self, market, monkeypatch):
        for i in range(I0, I0 + 8):
            run(i)
        rep = mr.report()
        assert rep["ok"] and rep["sessions_saved"] == 8 and rep["stocks"] == 3
        assert [f["symbol"] for f in rep["focus"]] == ["CLSK", "RIOT", "NVDA"]
        pooled = rep["pooled"]
        assert pooled["days"]["1"] == 7 and pooled["verdict"] is None       # too early
        assert sum(b["n"] for b in pooled["bins"]) == pooled["cells"]
        monkeypatch.setattr(mr, "MIN_DAYS_POOLED", 5)
        mr._report_cache = None
        assert mr.report()["pooled"]["verdict"] in (
            "more accurate than its usual odds", "about as accurate as its usual odds",
            "less accurate than its usual odds")

    def test_live_for_one_stock(self, market):
        for i in range(I0, I0 + 3):
            run(i)
        live = mr.live_for("clsk")
        assert live["since"] == str(DAYS[I0]) and live["days"]["1"] == 2 and live["verdict"] is None
        assert mr.live_for("AAPL") == {"since": str(DAYS[I0]), "last_saved": str(DAYS[I0 + 2]), "days": None}

    def test_the_map_carries_its_live_record(self, market, monkeypatch):
        from src.data import fmp_client
        monkeypatch.setattr(fmp_client, "get_symbol_next_earnings", lambda s, today=None: (False, None))
        monkeypatch.setattr(pm, "calibrate", lambda p, sessions=0: None)
        pm._cache.clear()
        for i in range(I0, I0 + 3):
            run(i)
        out = pm.probability_map("CLSK", now=evening(N - 1))
        assert out["live"]["days"]["1"] == 2
        pm._cache.clear()

    def test_route(self, market):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        run(I0)
        app = FastAPI()
        app.include_router(router)
        body = TestClient(app).get("/probability-map-record").json()
        assert body["ok"] and body["since"] == str(DAYS[I0]) and body["waiting"] == [str(DAYS[I0])]


class TestWiring:
    def test_universe(self):
        u = mr.universe()
        assert u[:6] == list(mr.FOCUS) and len(u) == len(set(u)) and not any("/" in s for s in u)
        assert {"CLSK", "MARA", "IREN"} <= set(u) and len(u) > 100

    def test_background_loop_runs_it_without_alerts(self):
        from src import main
        src = inspect.getsource(main._refresh_loop)
        block = src[src.index("map_record.due()"):src.index("Map record failed")]
        assert "map_record.needs_work()" in block and 'heavy.should_skip("map record")' in block
        assert 'heavy.run("map record", map_record.run_daily)' in block
        assert "dispatch" not in block and "telegram" not in block.lower()
        # after the scan's own error handler, so a failed scan cannot skip it
        assert src.index("Background refresh failed") < src.index("map_record.due()")


class TestReviewFindings:
    def _evenings(self, seq, market):
        """Run each evening in seq; ("glitch", i) runs evening i while SPY's
        bars briefly lack session i."""
        mr._mem.clear()
        for i in seq:
            if isinstance(i, tuple):
                i = i[1]
                spy = market["bars"]["SPY"]
                market["bars"]["SPY"] = spy.drop(spy.index[i])
                assert run(i) is None
                market["bars"]["SPY"] = spy
            else:
                run(i)
        return score()

    def test_a_calendar_that_goes_back_a_session_changes_nothing(self, market):
        clean = self._evenings(range(I0, I0 + 8), market)
        glitched = self._evenings([I0, I0 + 1, ("glitch", I0 + 1)] + list(range(I0 + 2, I0 + 8)), market)
        assert glitched["symbols"] == clean["symbols"] and glitched["days"] == clean["days"]
        assert glitched["snapshots"] == clean["snapshots"] == 8

    def test_saved_tables_are_kept_apart_by_version(self, market, monkeypatch):
        run(I0)
        v1 = snap(I0)
        monkeypatch.setattr(pm, "METHOD_VERSION", 2)
        run(I0)
        assert mr.snap_key(str(DAYS[I0]), 1) != mr.snap_key(str(DAYS[I0]), 2)
        assert json.loads(mr._mem[mr.snap_key(str(DAYS[I0]), 1)]) == v1           # not overwritten
        monkeypatch.setattr(pm, "METHOD_VERSION", 1)
        run(I0 + 1)
        assert score()["days"]["1"] == 1

    def test_a_stock_without_data_is_reported(self, market):
        del market["bars"]["NVDA"]
        assert run(I0) == f"saved 2 stocks for {DAYS[I0]} (1 without a table); scored 0 stock windows from 0 earlier sessions"

    def test_a_stock_dropped_from_the_list_is_still_scored(self, market):
        run(I0)
        run(I0 + 1, symbols=["CLSK", "RIOT"])
        assert score()["symbols"]["NVDA"]["h"]["1"][0] == 8

    def test_a_halted_stock_scores_the_same_whenever_the_run_happens(self, market):
        nv = market["bars"]["NVDA"]
        market["bars"]["NVDA"] = nv.drop(nv.index[I0 + 1:I0 + 3])           # no trades for two sessions
        # evenings during the halt save no NVDA table, so both runs hold the same NVDA tables
        timely = self._evenings([I0, I0 + 1, I0 + 2, I0 + 5], market)["symbols"]["NVDA"]
        late = self._evenings([I0, I0 + 5], market)["symbols"]["NVDA"]
        assert timely["h"]["1"][0] == late["h"]["1"][0] == 0                 # no bar in the window
        assert timely["next"][0] == late["next"][0] == 0                     # no bar on the next session
        assert timely["h"]["5"] == late["h"]["5"] and timely["h"]["5"][0] == 8

    def test_a_failed_score_write_after_the_tables_are_saved(self, market, monkeypatch):
        class Flaky(TestStorage.FakeRedis):
            def __init__(self):
                super().__init__()
                self.fail_score_once = True

            def set(self, key, value, ex=None):
                if key == mr.score_key() and self.fail_score_once and mr.snap_key(str(DAYS[I0 + 1])) in self.data:
                    self.fail_score_once = False
                    raise ConnectionError("upstash write failed")
                super().set(key, value, ex)

        r = Flaky()
        monkeypatch.setattr(mr, "_redis", lambda: r)
        run(I0)
        with pytest.raises(ConnectionError):
            run(I0 + 1)
        run(I0 + 1)
        flaky = json.loads(r.data[mr.score_key()])
        r2 = TestStorage.FakeRedis()
        monkeypatch.setattr(mr, "_redis", lambda: r2)
        run(I0)
        run(I0 + 1)
        clean = json.loads(r2.data[mr.score_key()])
        assert flaky["symbols"] == clean["symbols"] and flaky["days"] == clean["days"]
        assert flaky["snapshots"] == clean["snapshots"] == 2

    def test_open_odds_cases_are_counted_on_their_own(self, market):
        market["bars"]["CLSK"].iloc[I0 + 1, 0] = np.nan                      # no open print
        run(I0)
        run(I0 + 1)
        nxt = mr.live_for("CLSK")["next"]
        assert nxt["days"] == 1 and nxt["open_days"] == 0


class TestFinalReview:
    def test_pooled_open_count_is_in_sessions_like_the_close_count(self, market):
        run(I0)
        run(I0 + 1)
        run(I0 + 2)
        nxt = mr.report()["pooled"]["next"]
        assert nxt["days"] == nxt["open_days"] == 2                      # sessions, not stock-sessions

    def test_a_saved_stock_shows_as_tracked_before_anything_is_scored(self, market):
        run(I0)
        live = mr.live_for("CLSK")
        assert live["days"] == {"1": 0, "5": 0, "10": 0, "20": 0, "n": 0, "o": 0} and live["verdict"] is None
        assert mr.live_for("AAPL")["days"] is None                          # really not tracked

    def test_a_short_calendar_writes_nothing_and_waits(self, market):
        run(I0)
        run(I0 + 3)
        before = dict(mr._mem)
        spy = market["bars"]["SPY"]
        market["bars"]["SPY"] = spy.iloc[I0 + 2:I0 + 5]                    # a truncated response
        with pytest.raises(RuntimeError, match="sessions in the SPY calendar"):
            run(I0 + 4)
        assert mr._mem == before and mr.due(evening(I0 + 4)) is False
        market["bars"]["SPY"] = spy
        run(I0 + 4)
        assert score()["days"]["5"] == 0 and str(DAYS[I0]) in score()["open"]   # nothing given up

    def test_many_saved_stocks_missing_from_a_fetch_is_a_data_problem(self, market, monkeypatch):
        monkeypatch.setattr(mr, "MISSING_OK", 1)
        run(I0)
        before = dict(mr._mem)
        saved = {s: market["bars"].pop(s) for s in ("RIOT", "NVDA")}
        with pytest.raises(RuntimeError, match="saved stocks came back without bars"):
            run(I0 + 1)
        assert mr._mem == before
        market["bars"].update(saved)
        run(I0 + 1)
        assert score()["symbols"]["NVDA"]["h"]["1"][0] == 8                  # scored on the retry

    def test_a_few_missing_stocks_are_logged_and_the_rest_scored(self, market, mse_logs):
        import logging
        logging.getLogger("mse.map_record").addHandler(mse_logs.handler)
        try:
            run(I0)
            del market["bars"]["NVDA"]
            run(I0 + 1)
        finally:
            logging.getLogger("mse.map_record").removeHandler(mse_logs.handler)
        assert "1 saved stocks came back without bars: NVDA" in mse_logs.text
        assert score()["symbols"]["CLSK"]["h"]["1"][0] == 8 and "NVDA" not in score()["symbols"]

    def test_no_bars_for_the_session_waits_instead_of_refetching(self, market):
        for s in SYMS:
            market["bars"][s] = market["bars"][s].iloc[:I0]                  # the session is not in yet
        assert run(I0) == f"saved 0 stocks for {DAYS[I0]} (3 without a table); scored 0 stock windows from 0 earlier sessions"
        assert mr.due(evening(I0)) is False                                  # held back for RETRY_EVERY
        assert mr.needs_work(evening(I0)) is True                            # and tried again after that

    def test_the_loop_as_it_runs_on_the_server(self, market):
        """Several loop passes per evening through due() and needs_work(),
        without resetting anything, give the same totals as one run each."""
        for i in range(I0, I0 + 6):
            for hh in (17, 18, 19):
                now = evening(i, hh)
                if mr.due(now) and mr.needs_work(now):
                    mr.run_daily(now=now, symbols=SYMS)
        looped = score()
        mr._mem.clear()
        for i in range(I0, I0 + 6):
            run(i)
        assert looped["symbols"] == score()["symbols"] and looped["days"] == score()["days"]
