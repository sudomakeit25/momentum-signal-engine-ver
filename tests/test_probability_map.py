"""Probability map: volatility-scaled odds of reaching levels around the
price, the next-session 10% odds, and the walk-forward check. No network."""

import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from src.scanner import probability_map as pm

ET = ZoneInfo("America/New_York")


def walk(sigmas, seed=1, start="2019-01-02", price=20.0):
    """Daily bars whose log returns have the given daily volatilities.
    Opens gap a little; highs and lows reach past the open and close."""
    rng = np.random.default_rng(seed)
    sig = np.asarray(sigmas, dtype=float)
    n = sig.size
    gaps = rng.normal(0, 0.3, n) * sig
    oc = rng.normal(0, math.sqrt(1 - 0.09), n) * sig
    close = price * np.exp(np.cumsum(gaps + oc))
    prev = np.r_[price, close[:-1]]
    opn = prev * np.exp(gaps)
    hi = np.maximum(opn, close) * np.exp(np.abs(rng.normal(0, 0.4, n)) * sig)
    lo = np.minimum(opn, close) * np.exp(-np.abs(rng.normal(0, 0.4, n)) * sig)
    idx = pd.bdate_range(start, periods=n, tz=ET)
    return pd.DataFrame({"open": opn, "high": hi, "low": lo, "close": close,
                         "volume": 1e6}, index=idx)


@pytest.fixture(autouse=True)
def _fresh_cache():
    pm._cache.clear()
    yield
    pm._cache.clear()


class TestVolatility:
    def test_steady_moves_give_their_size(self):
        r = 0.03
        close = 10 * np.exp(np.cumsum([r if i % 2 else -r for i in range(300)]))
        sig = pm.daily_vol(close)
        assert sig[-1] == pytest.approx(r, rel=1e-6)

    def test_warmup_then_values(self):
        sig = pm.daily_vol(10 * np.exp(np.cumsum(np.full(60, 0.01))))
        assert np.isnan(sig[: pm.WARMUP]).all() and np.isfinite(sig[pm.WARMUP:]).all()

    def test_flat_prices_hit_the_floor_not_zero(self):
        assert pm.daily_vol(np.full(50, 7.0))[-1] == pm.VOL_FLOOR

    def test_empty(self):
        assert pm.daily_vol([]).size == 0

    def test_uses_only_the_past(self):
        a = 10 * np.exp(np.cumsum(np.random.default_rng(3).normal(0, 0.02, 200)))
        b = a.copy()
        b[150:] *= 3                              # a different future
        assert np.array_equal(pm.daily_vol(a)[:150], pm.daily_vol(b)[:150], equal_nan=True)


class TestForwardMoves:
    D = pd.DataFrame({"open": [10, 10, 11, 9], "high": [10.5, 11.5, 9.5, 12.5],
                      "low": [9.5, 10.5, 8.5, 11.5], "close": [10.0, 11.0, 9.0, 12.0]})

    def test_one_session(self):
        up, dn, cl = pm.forward_moves(self.D, 1)
        assert up[0] == pytest.approx(math.log(11.5 / 10)) and dn[0] == pytest.approx(math.log(10.5 / 10))
        assert cl[0] == pytest.approx(math.log(11 / 10)) and math.isnan(up[3]) and math.isnan(cl[3])

    def test_two_sessions(self):
        up, dn, cl = pm.forward_moves(self.D, 2)
        assert up[0] == pytest.approx(math.log(11.5 / 10)) and dn[0] == pytest.approx(math.log(8.5 / 10))
        assert cl[0] == pytest.approx(math.log(9 / 10)) and up[1] == pytest.approx(math.log(12.5 / 11))
        assert np.isnan(up[2:]).all() and np.isnan(cl[2:]).all()

    def test_longer_than_the_data(self):
        up, dn, cl = pm.forward_moves(self.D, 10)
        assert np.isnan(up).all() and np.isnan(cl).all() and cl.size == 4


class TestOdds:
    def test_shape_and_order(self):
        p = pm.prepare(pm.clean_bars(walk(np.full(800, 0.03))))
        g = pm.grid_at(p, len(p["close"]) - 1)
        for k in ("up", "dn", "usual_up", "usual_dn"):
            a = g[k]
            assert a.shape == (len(pm.HORIZONS), len(pm.LEVELS)) and ((a >= 0) & (a <= 1)).all()
            assert (np.diff(a, axis=0) >= 0).all(), k        # a longer window never has lower odds
            assert (np.diff(a, axis=1) <= 0).all(), k        # a farther level never has higher odds

    def test_matches_an_independent_run_of_the_same_process(self):
        sig = 0.025
        p = pm.prepare(pm.clean_bars(walk(np.full(1500, sig), seed=5)))
        g = pm.grid_at(p, len(p["close"]) - 1)
        # the true frequencies, from a much longer independent series
        truth = pm.clean_bars(walk(np.full(20000, sig), seed=99))
        i5 = pm.HORIZONS.index(5)
        up, dn, _ = pm.forward_moves(truth, 5)
        for j, lvl in enumerate(pm.LEVELS[:2]):
            assert g["up"][i5][j] == pytest.approx(np.nanmean(up >= math.log1p(lvl / 100)), abs=0.05)
            assert g["dn"][i5][j] == pytest.approx(np.nanmean(dn <= math.log1p(-lvl / 100)), abs=0.05)

    def test_a_loud_stock_gets_wider_odds_than_usual_and_a_quiet_one_narrower(self):
        loud = pm.prepare(pm.clean_bars(walk(np.r_[np.full(1000, 0.01), np.full(80, 0.05)], seed=2)))
        quiet = pm.prepare(pm.clean_bars(walk(np.r_[np.full(1000, 0.05), np.full(80, 0.01)], seed=2)))
        i5, j10 = pm.HORIZONS.index(5), pm.LEVELS.index(10.0)
        gl, gq = pm.grid_at(loud, 1079), pm.grid_at(quiet, 1079)
        assert gl["up"][i5][j10] > 3 * gl["usual_up"][i5][j10] and gl["up"][i5][j10] > 0.2
        # the long half of the volatility still remembers the loud years, so calm is believed slowly
        assert gq["up"][i5][j10] < gq["usual_up"][i5][j10] / 2

    def test_too_little_history_gives_none(self):
        p = pm.prepare(pm.clean_bars(walk(np.full(200, 0.02))))
        assert pm.grid_at(p, 199) is None and pm.big_day_at(p, 199) is None

    def test_no_hindsight(self):
        d = pm.clean_bars(walk(np.full(900, 0.03), seed=8))
        t = 700
        changed = d.copy()
        changed.iloc[t + 1:, :4] *= 1.7                         # a very different future
        a, b = pm.prepare(d.iloc[: t + 1]), pm.prepare(changed)
        ga, gb = pm.grid_at(a, t), pm.grid_at(b, t)
        for k in ("up", "dn", "usual_up", "usual_dn"):
            assert np.array_equal(ga[k], gb[k], equal_nan=True)
        assert pm.big_day_at(a, t) == pm.big_day_at(b, t)
        assert pm.open_odds_at(a, t, 30.0) == pm.open_odds_at(b, t, 30.0)

    def test_the_open_moves_the_odds_the_right_way(self):
        p = pm.prepare(pm.clean_bars(walk(np.full(900, 0.04), seed=4)))
        t, c = 899, p["close"][899]
        flat, up_gap, down_gap = (pm.open_odds_at(p, t, c * f) for f in (1.0, 1.08, 0.92))
        assert up_gap["up"] > flat["up"] > down_gap["up"]
        assert down_gap["down"] > flat["down"] > up_gap["down"]
        assert pm.open_odds_at(p, t, c * 1.12)["up"] > 0.5      # opened past the level already
        assert up_gap["gap_pct"] == pytest.approx(8.0, abs=1e-9)
        assert pm.open_odds_at(p, t, 0) is None and pm.open_odds_at(p, t, -3) is None


class TestCheck:
    def test_changing_volatility_shows_skill(self):
        blocks = np.concatenate([np.full(120, s) for s in (0.01, 0.045) * 7])
        cal = pm.calibrate(pm.prepare(pm.clean_bars(walk(blocks, seed=11))))
        g = cal["grid"]
        assert g["sessions"] == pm.CAL_SESSIONS
        assert 1 - g["brier_model"] / g["brier_usual"] > 0.05

    def test_steady_volatility_shows_no_made_up_skill(self):
        cal = pm.calibrate(pm.prepare(pm.clean_bars(walk(np.full(1300, 0.03), seed=12))))
        g = cal["grid"]
        assert abs(1 - g["brier_model"] / g["brier_usual"]) < 0.03

    def test_bins_and_counts(self):
        cal = pm.calibrate(pm.prepare(pm.clean_bars(walk(np.full(1000, 0.04), seed=13))))
        g, b = cal["grid"], cal["big_day"]
        assert sum(x["n"] for x in g["bins"]) == g["count"]
        assert g["count"] == g["sessions"] * 2 * len(pm.HORIZONS) * len(pm.LEVELS)
        assert all(0 <= x["said"] <= 1 and 0 <= x["happened"] <= 1 for x in g["bins"])
        assert b["count"] == 2 * b["sessions"] and b["count_open"] == b["count"]

    @pytest.mark.parametrize("skill,text", [(0.05, "more accurate than its usual odds"),
                                            (0.02, "more accurate than its usual odds"),
                                            (0.0, "about as accurate as its usual odds"),
                                            (-0.02, "less accurate than its usual odds"),
                                            (None, None)])
    def test_verdict(self, skill, text):
        assert pm.verdict(skill) == text


class TestBuild:
    def test_full_answer(self):
        bars = walk(np.full(1000, 0.04), seed=21)
        out = pm.build(bars, today_open=float(bars["close"].iloc[-1]) * 1.05, today=date(2026, 11, 18))
        assert out["data_ok"] and out["as_of"] == str(bars.index[-1].date())
        assert [r["level_pct"] for r in out["rows"]] == [30, 20, 10, 5, -5, -10, -20, -30]
        last = out["last_close"]
        assert out["rows"][2]["price"] == pytest.approx(last * 1.10, rel=1e-4)
        assert out["rows"][-1]["price"] == pytest.approx(last * 0.70, rel=1e-4)
        assert all(len(r["odds"]) == len(pm.HORIZONS) == len(r["usual"]) for r in out["rows"])
        assert out["today"]["gap_pct"] == pytest.approx(5.0, abs=1e-3) and out["today"]["date"] == "2026-11-18"
        assert out["today"]["up"] > out["big_day"]["up"]          # opened 5% up: closer to +10%
        cal = out["calibration"]
        assert cal["sessions"] >= pm.MIN_CAL and cal["verdict"] and cal["big_day"]["verdict"]

    def test_short_history(self):
        out = pm.build(walk(np.full(120, 0.02)))
        assert out["data_ok"] is False and "120 sessions" in out["note"]

    def test_empty_and_none(self):
        assert pm.build(pd.DataFrame())["data_ok"] is False
        assert pm.build(None)["data_ok"] is False

    def test_order_duplicates_and_bad_rows_do_not_matter(self):
        bars = walk(np.full(700, 0.03), seed=22)
        messy = pd.concat([bars.iloc[::-1], bars.iloc[100:105]])     # reversed, with repeats
        bad = bars.iloc[:3].copy()
        bad["close"] = [0.0, -1.0, np.nan]
        bad.index = pd.bdate_range("2010-01-04", periods=3, tz=ET)  # junk rows dropped, not used
        a = pm.build(bars, check=False)
        b = pm.build(pd.concat([messy, bad]), check=False)
        assert a == b

    def test_no_today_without_an_open(self):
        assert pm.build(walk(np.full(700, 0.03)), today_open=None, check=False)["today"] is None


class TestProbabilityMap:
    @pytest.fixture
    def feed(self, monkeypatch):
        calls = []
        bars = walk(np.full(800, 0.04), seed=31, start="2023-09-12")
        from src.data import client, fmp_client

        def fake(symbols, days=200, **kw):
            calls.append((tuple(symbols), days))
            return {s: bars for s in symbols}

        monkeypatch.setattr(client, "get_multi_bars", fake)
        monkeypatch.setattr(fmp_client, "get_symbol_next_earnings", lambda s, today=None: (True, "2026-12-03"))
        return bars, calls

    def test_after_the_close_the_last_bar_is_the_origin(self, feed):
        bars, calls = feed
        last = bars.index[-1]
        out = pm.probability_map("clsk", now=datetime(last.year, last.month, last.day, 17, 0, tzinfo=ET))
        assert out["symbol"] == "CLSK" and out["data_ok"] and out["in_progress"] is False
        assert out["as_of"] == str(last.date()) and out["today"] is None
        assert calls == [(("CLSK",), pm.HISTORY_DAYS)]

    def test_during_the_session_the_open_updates_the_odds(self, feed):
        bars, _ = feed
        last = bars.index[-1]
        out = pm.probability_map("CLSK", now=datetime(last.year, last.month, last.day, 11, 0, tzinfo=ET))
        assert out["in_progress"] is True
        assert out["as_of"] == str(bars.index[-2].date())          # the session before today
        assert out["today"]["open"] == pytest.approx(bars["open"].iloc[-1], rel=1e-4)
        assert out["last_close"] == pytest.approx(bars["close"].iloc[-2], rel=1e-4)

    def test_earnings_are_reported(self, feed):
        bars, _ = feed
        out = pm.probability_map("CLSK", now=datetime(2026, 11, 18, 17, 0, tzinfo=ET))
        assert out["earnings"]["known"] and out["earnings"]["date"] == "2026-12-03"
        assert out["earnings"]["sessions_away"] == int(np.busday_count(date.fromisoformat(out["as_of"]),
                                                                       date(2026, 12, 3)))

    def test_cached(self, feed):
        _, calls = feed
        pm.probability_map("CLSK")
        pm.probability_map("CLSK")
        assert len(calls) == 1

    def test_cache_is_bounded(self, feed, monkeypatch):
        monkeypatch.setattr(pm, "_CACHE_MAX", 3)
        monkeypatch.setattr(pm, "calibrate", lambda p, sessions=0: None)       # speed
        for s in ("AA", "BB", "CC", "DD", "EE"):
            pm.probability_map(s)
        assert len(pm._cache) == 3 and set(pm._cache) == {"CC", "DD", "EE"}

    @pytest.mark.parametrize("sym", ["", "  ", ".AB", "TOO-LONG-SYMBOL", "AB$", "<script>"])
    def test_bad_symbols_fetch_nothing(self, feed, sym):
        _, calls = feed
        out = pm.probability_map(sym)
        assert out["data_ok"] is False and calls == []

    def test_a_data_failure_is_not_raised(self, monkeypatch):
        from src.data import client

        def boom(*a, **k):
            raise RuntimeError("alpaca down")

        monkeypatch.setattr(client, "get_multi_bars", boom)
        out = pm.probability_map("CLSK")
        assert out == {"symbol": "CLSK", "data_ok": False, "note": "Could not build the map right now.",
                       "retry": True}
        assert pm._cache == {}                                     # failures are not cached

    def test_no_history(self, monkeypatch):
        from src.data import client
        monkeypatch.setattr(client, "get_multi_bars", lambda s, days=0, **k: {})
        assert pm.probability_map("ZZZZ")["note"] == "No price history for ZZZZ."

    def test_route(self, feed):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        app = FastAPI()
        app.include_router(router)
        r = TestClient(app).get("/probability-map/clsk")
        assert r.status_code == 200
        body = r.json()
        assert body["symbol"] == "CLSK" and body["data_ok"] and len(body["rows"]) == 8


def _ewm_var(r2, hl, t):
    """pandas-style adjusted exponential mean of r2[1..t], written out."""
    a = 1 - 0.5 ** (1 / hl)
    obs = [(k, r2[k]) for k in range(1, t + 1)]
    if len(obs) < pm.WARMUP:
        return float("nan")
    w = [(1 - a) ** (t - k) for k, _ in obs]
    return sum(wi * v for wi, (_, v) in zip(w, obs)) / sum(w)


class TestBruteForce:
    """calibrate() against a slow recount written straight from the definitions."""

    def test_check_matches_a_recount(self):
        d = pm.clean_bars(walk(np.full(330, 0.06), seed=41))
        c, hi, lo, o = (d[k].to_numpy(float) for k in ("close", "high", "low", "open"))
        n, H, S = len(c), max(pm.HORIZONS), 15
        r2 = np.r_[np.nan, np.diff(np.log(c)) ** 2]
        sig = [math.sqrt(0.5 * _ewm_var(r2, 10, t) + 0.5 * _ewm_var(r2, 160, t)) if t >= pm.WARMUP else float("nan")
               for t in range(n)]
        sig = [max(s, pm.VOL_FLOOR) if math.isfinite(s) else s for s in sig]
        ext = {h: ([max(hi[s + 1:s + h + 1]) if s + h < n else None for s in range(n)],
                   [min(lo[s + 1:s + h + 1]) if s + h < n else None for s in range(n)]) for h in pm.HORIZONS}
        gm = gu = 0.0
        for t in range(n - 1 - H - S + 1, n - H):
            hist = [s for s in range(t - H + 1) if math.isfinite(sig[s])]
            for h in pm.HORIZONS:
                up, dn = ext[h]
                for L in pm.LEVELS:
                    a, b = math.log1p(L / 100), math.log1p(-L / 100)
                    for side in ("up", "dn"):
                        if side == "up":
                            model = np.mean([math.log(up[s] / c[s]) / sig[s] >= a / sig[t] for s in hist])
                            usual = np.mean([math.log(up[s] / c[s]) >= a for s in hist])
                            hit = math.log(up[t] / c[t]) >= a
                        else:
                            model = np.mean([math.log(dn[s] / c[s]) / sig[s] <= b / sig[t] for s in hist])
                            usual = np.mean([math.log(dn[s] / c[s]) <= b for s in hist])
                            hit = math.log(dn[t] / c[t]) <= b
                        gm += (model - hit) ** 2
                        gu += (usual - hit) ** 2
        bm = bu = bo = 0.0
        up10, dn10 = math.log1p(0.1), math.log1p(-0.1)
        for t in range(n - 1 - S, n - 1):
            hist = [s for s in range(t) if math.isfinite(sig[s])]
            nxt = math.log(c[t + 1] / c[t])
            g = math.log(o[t + 1] / c[t])
            for lvl, ge in ((up10, True), (dn10, False)):
                hit = nxt >= lvl if ge else nxt <= lvl
                z = [math.log(c[s + 1] / c[s]) / sig[s] for s in hist]
                zo = [math.log(c[s + 1] / o[s + 1]) / sig[s] for s in hist]
                raw = [math.log(c[s + 1] / c[s]) for s in hist]
                if ge:
                    model, usual = np.mean([x >= lvl / sig[t] for x in z]), np.mean([x >= lvl for x in raw])
                    opened = np.mean([x >= (lvl - g) / sig[t] for x in zo])
                else:
                    model, usual = np.mean([x <= lvl / sig[t] for x in z]), np.mean([x <= lvl for x in raw])
                    opened = np.mean([x <= (lvl - g) / sig[t] for x in zo])
                bm += (model - hit) ** 2
                bu += (usual - hit) ** 2
                bo += (opened - hit) ** 2
        cal = pm.calibrate(pm.prepare(d), sessions=S)
        g_, b_ = cal["grid"], cal["big_day"]
        assert g_["sessions"] == S and b_["sessions"] == S
        assert g_["brier_model"] == pytest.approx(gm, rel=1e-9) and g_["brier_usual"] == pytest.approx(gu, rel=1e-9)
        assert b_["brier_model"] == pytest.approx(bm, rel=1e-9) and b_["brier_usual"] == pytest.approx(bu, rel=1e-9)
        assert b_["brier_open"] == pytest.approx(bo, rel=1e-9)
        assert b_["happened"] > 0                                    # the 10% case was really exercised


class TestReviewFindings:
    def test_missing_opens_are_left_out_of_the_open_check(self):
        bars = walk(np.full(800, 0.04), seed=42)
        bars.iloc[700:780:3, bars.columns.get_loc("open")] = np.nan
        b = pm.calibrate(pm.prepare(pm.clean_bars(bars)))["big_day"]
        assert 0 < b["count_open"] < b["count"]

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 0.0, -5.0, None])
    def test_unusable_opens_give_no_today(self, bad):
        p = pm.prepare(pm.clean_bars(walk(np.full(700, 0.03))))
        assert pm.open_odds_at(p, 699, bad) is None
        assert pm.build(walk(np.full(700, 0.03)), today_open=bad, check=False)["today"] is None

    def test_short_history_shows_the_10pct_check_with_its_own_dates(self):
        out = pm.build(walk(np.full(390, 0.05), seed=43))
        cal = out["calibration"]
        assert cal["sessions"] == 0 and "verdict" not in cal          # the grid check is too short
        b = cal["big_day"]
        assert b["sessions"] >= pm.MIN_CAL and b["from"] < b["to"] <= out["as_of"]


class TestServing:
    @pytest.fixture
    def feed(self, monkeypatch):
        calls = []
        bars = walk(np.full(800, 0.04), seed=51, start="2023-09-12")
        from src.data import client, fmp_client

        def fake(symbols, days=200, **kw):
            calls.append(tuple(symbols))
            return {s: bars.copy() for s in symbols}

        monkeypatch.setattr(client, "get_multi_bars", fake)
        monkeypatch.setattr(fmp_client, "get_symbol_next_earnings", lambda s, today=None: (False, None))
        return bars, calls

    def _at(self, bars, hh, mm):
        last = bars.index[-1]
        return datetime(last.year, last.month, last.day, hh, mm, tzinfo=ET)

    def test_parallel_requests_never_raise(self, feed, monkeypatch):
        import sys
        import threading
        monkeypatch.setattr(pm, "_CACHE_MAX", 4)
        monkeypatch.setattr(pm, "calibrate", lambda p, sessions=0: None)
        errors, old = [], sys.getswitchinterval()

        def run(sym):
            try:
                assert pm.probability_map(sym)["data_ok"]
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        sys.setswitchinterval(1e-6)
        try:
            threads = [threading.Thread(target=run, args=(chr(65 + i) * 2,)) for i in range(16)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            sys.setswitchinterval(old)
        assert errors == [] and len(pm._cache) <= 4

    def test_same_symbol_at_once_is_built_once(self, feed, monkeypatch):
        import threading
        _, calls = feed
        monkeypatch.setattr(pm, "calibrate", lambda p, sessions=0: None)
        threads = [threading.Thread(target=pm.probability_map, args=("CLSK",)) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert calls == [("CLSK",)]

    @pytest.mark.parametrize("hh,mm,live", [(16, 14, True), (16, 16, False)])
    def test_the_session_counts_as_live_until_16_15(self, feed, hh, mm, live):
        bars, _ = feed
        out = pm.probability_map("CLSK", now=self._at(bars, hh, mm))
        assert out["in_progress"] is live and (out["today"] is not None) is live

    def test_before_the_open_todays_bar_is_dropped_and_not_used(self, feed):
        bars, _ = feed
        out = pm.probability_map("CLSK", now=self._at(bars, 9, 0))
        assert out["as_of"] == str(bars.index[-2].date()) and out["today"] is None

    def test_an_open_outside_the_sessions_range_is_ignored(self, feed):
        bars, _ = feed
        bars.iloc[-1, bars.columns.get_loc("open")] = bars["high"].iloc[-1] * 1.5
        out = pm.probability_map("CLSK", now=self._at(bars, 11, 0))
        assert out["in_progress"] is True and out["today"] is None

    def test_a_short_history_answer_is_cached_too(self, monkeypatch):
        from src.data import client
        calls = []
        monkeypatch.setattr(client, "get_multi_bars",
                            lambda s, days=0, **k: calls.append(1) or {s[0]: walk(np.full(100, 0.02))})
        assert pm.probability_map("NEWCO")["data_ok"] is False
        assert pm.probability_map("NEWCO")["data_ok"] is False and len(calls) == 1

    def test_numeric_tickers_are_allowed(self, feed):
        _, calls = feed
        assert pm.probability_map("7203.T")["data_ok"] and calls == [("7203.T",)]

    def test_route_with_a_bad_symbol(self, feed):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        app = FastAPI()
        app.include_router(router)
        r = TestClient(app).get("/probability-map/AB%24")
        assert r.status_code == 200 and r.json() == {"symbol": "AB$", "data_ok": False, "note": "Not a stock symbol."}


class TestBusy:
    @pytest.fixture
    def slow_feed(self, monkeypatch):
        import threading
        bars = walk(np.full(800, 0.04), seed=61)
        from src.data import client, fmp_client
        gate = threading.Event()
        calls = []

        def fake(symbols, days=200, **kw):
            calls.append(tuple(symbols))
            gate.wait(5)                                  # a slow download
            return {s: bars.copy() for s in symbols}

        monkeypatch.setattr(client, "get_multi_bars", fake)
        monkeypatch.setattr(fmp_client, "get_symbol_next_earnings", lambda s, today=None: (False, None))
        monkeypatch.setattr(pm, "calibrate", lambda p, sessions=0: None)
        return gate, calls

    def test_a_slow_download_does_not_block_another_stock(self, monkeypatch):
        import threading
        bars = walk(np.full(800, 0.04), seed=62)
        from src.data import client, fmp_client
        stalled = threading.Event()

        def fake(symbols, days=200, **kw):
            if "AAA" in symbols:
                stalled.wait(10)                          # AAA's download hangs
            return {s: bars.copy() for s in symbols}

        monkeypatch.setattr(client, "get_multi_bars", fake)
        monkeypatch.setattr(fmp_client, "get_symbol_next_earnings", lambda s, today=None: (False, None))
        monkeypatch.setattr(pm, "calibrate", lambda p, sessions=0: None)
        monkeypatch.setattr(pm, "BUILD_WAIT", 1)
        first = threading.Thread(target=pm.probability_map, args=("AAA",))
        first.start()
        try:
            out = pm.probability_map("BBB")               # while AAA is still downloading
            assert out["data_ok"] and first.is_alive()
        finally:
            stalled.set()
            first.join()

    def test_same_stock_waits_for_the_running_build(self, slow_feed):
        import threading
        gate, calls = slow_feed
        results = []
        threads = [threading.Thread(target=lambda: results.append(pm.probability_map("CCC"))) for _ in range(4)]
        for th in threads:
            th.start()
        gate.set()
        for th in threads:
            th.join()
        assert calls == [("CCC",)] and all(r["data_ok"] for r in results)

    def test_busy_calculation_slot_is_temporary_and_not_cached(self, slow_feed, monkeypatch):
        gate, _ = slow_feed
        gate.set()
        monkeypatch.setattr(pm, "BUILD_WAIT", 0.2)
        assert pm._cpu_slot.acquire(timeout=1)            # someone else is calculating
        try:
            out = pm.probability_map("DDD")
        finally:
            pm._cpu_slot.release()
        assert out == {"symbol": "DDD", "data_ok": False, "note": pm.BUSY, "retry": True}
        assert "DDD" not in pm._cache
        assert pm.probability_map("DDD")["data_ok"]       # and the next request builds it
