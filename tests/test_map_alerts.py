"""Probability map alerts (digest, volatility shift, big open, price levels)
and their delivery to Telegram and SMS, including SMS over Brevo's HTTPS
API. Synthetic data; nothing is sent anywhere."""

import inspect
import math
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from src.data import client
from src.notifications import dispatcher, map_alerts as ma
from src.notifications import alert_rules
from src.scanner import map_record
from src.scanner import probability_map as pm

ET = ZoneInfo("America/New_York")
REAL_SESSION_CLOSE = ma.session_close        # conftest replaces it with a fixed 16:00


def walk(n, sig, seed, price=20.0, start="2023-06-01"):
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
                        index=pd.bdate_range(start, periods=n, tz=ET))


BARS = {"AAA": walk(900, 0.05, 1), "BBB": walk(900, 0.02, 2, price=150.0)}
DAYS = [t.date() for t in BARS["AAA"].index]
AS_OF = DAYS[-1]


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(ma, "_send", lambda kind, tg, sms: out.append((kind, tg, sms)) or {"telegram": True, "sms": len(sms)})
    return out


@pytest.fixture
def market(monkeypatch):
    calls = []

    def fake(symbols, days=200, **kw):
        calls.append(tuple(symbols))
        return {s: BARS[s].copy() for s in symbols if s in BARS}

    monkeypatch.setattr(client, "get_multi_bars", fake)
    monkeypatch.setattr(ma, "watchlist", lambda: ["AAA", "BBB"])
    monkeypatch.setattr(map_record, "sessions", lambda now: [d for d in DAYS if d <= now.date()][-60:])
    monkeypatch.setattr(alert_rules, "trading_day", lambda day: day.weekday() < 5)
    monkeypatch.setattr(pm, "_earnings", lambda sym, last: {"known": False, "date": None, "sessions_away": None})
    return calls


def at(day, hh, mm=0):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=ET)


# ---------------------------------------------------------------- level odds

class TestLevelOdds:
    def test_matches_the_grid_at_a_grid_level(self):
        p = pm.prepare(pm.clean_bars(BARS["AAA"]))
        t = len(p["close"]) - 1
        g = pm.grid_at(p, t)
        j = pm.LEVELS.index(10.0)
        up = pm.level_odds(p, t, p["close"][t] * 1.10)
        dn = pm.level_odds(p, t, p["close"][t] * 0.90)
        for i, h in enumerate(pm.HORIZONS):
            assert up["within"][h] == pytest.approx(g["up"][i][j])
            assert dn["within"][h] == pytest.approx(g["dn"][i][j])
        assert up["pct"] == pytest.approx(10.0) and 0 <= up["held5"] <= 1 and up["touches"] > 0

    @pytest.mark.parametrize("price", [None, "x", 0, -1, float("nan")])
    def test_unusable_prices(self, price):
        p = pm.prepare(pm.clean_bars(BARS["AAA"]))
        assert pm.level_odds(p, len(p["close"]) - 1, price) is None

    def test_the_close_itself_and_short_history(self):
        p = pm.prepare(pm.clean_bars(BARS["AAA"]))
        t = len(p["close"]) - 1
        assert pm.level_odds(p, t, p["close"][t]) is None
        short = pm.prepare(pm.clean_bars(BARS["AAA"].iloc[:150]))
        assert pm.level_odds(short, 149, 25.0) is None


# ---------------------------------------------------------------- evening digest

class TestDigest:
    def test_sent_once_per_session(self, market, sent):
        now = at(AS_OF, 16, 40)
        assert ma.evening_due(now)
        out = ma.evening(now)
        assert out.startswith(f"digest for {AS_OF}: 2 stocks")
        kinds = [k for k, _, _ in sent]
        assert kinds.count("digest") == 1
        assert ma.evening(now) is None and not ma.evening_due(now)
        ma._digest_done_for = None                              # a restart: the stored state still stops it
        assert ma.evening(now) is None and [k for k, _, _ in sent].count("digest") == 1

    def test_digest_text(self, market, sent):
        ma.evening(at(AS_OF, 16, 40))
        _, tg, sms = next(x for x in sent if x[0] == "digest")
        assert "MSE probability map" in tg and "AAA $" in tg and "BBB $" in tg
        assert "10%+ close next session" in tg and "Today: high" in tg
        assert "Live record: nothing scored yet." in tg and tg.rstrip().endswith("Past frequencies, not forecasts.")
        assert sms and all(len(x) <= ma.SMS_MAX for x in sms) and sms[0].startswith("MSE odds")
        assert "AAA" in " ".join(sms) and "BBB" in " ".join(sms)

    def test_many_stocks_say_the_rest_are_on_telegram(self, market):
        info = ma.stock_info("AAA", AS_OF)
        stocks = [{**info, "symbol": f"S{i:02d}"} for i in range(12)]
        _, sms = ma.format_digest(AS_OF, stocks, None)
        assert len(sms) == ma.SMS_TEXTS == dispatcher.MAP_SMS_PER_ALERT
        assert all(len(x) <= ma.SMS_MAX for x in sms) and "more stocks on Telegram" in sms[-1]
        shown = sum(x.count("S") for x in sms)              # stock lines start with "S.."
        assert shown + int(sms[-1].split("+")[-1].split()[0]) >= 12

    def test_reached_levels_match_the_session(self, market):
        info = ma.stock_info("AAA", AS_OF)
        d = pm.clean_bars(BARS["AAA"])
        c0, row = d["close"].iloc[-2], d.iloc[-1]
        for x in info["levels"]:
            lvl = x["level"]
            expect = row["high"] / c0 - 1 >= lvl / 100 if lvl > 0 else row["low"] / c0 - 1 <= lvl / 100
            assert x["hit"] == bool(expect)

    @pytest.mark.parametrize("now,fresh", [
        (lambda: at(AS_OF, 16, 30), True),                       # that evening
        (lambda: at(AS_OF + timedelta(days=1), 8, 0) if AS_OF.weekday() < 4 else at(AS_OF + timedelta(days=3), 8, 0), True),
        (lambda: at(AS_OF + timedelta(days=1), 11, 0) if AS_OF.weekday() < 4 else at(AS_OF + timedelta(days=3), 11, 0), False),
    ])
    def test_only_until_the_next_open(self, market, now, fresh, monkeypatch):
        monkeypatch.setattr(map_record, "sessions", lambda n: [d for d in DAYS if d <= AS_OF][-60:])
        assert ma._fresh(AS_OF, now()) is fresh

    def test_weekend_still_fresh(self, market):
        sat = AS_OF + timedelta(days=(5 - AS_OF.weekday()) % 7 or 7)
        assert ma._fresh(AS_OF, at(sat, 13, 0)) is True

    def test_no_data_is_not_marked_sent(self, market, sent, monkeypatch):
        monkeypatch.setattr(client, "get_multi_bars", lambda symbols, days=200, **kw: {})
        assert ma.evening(at(AS_OF, 16, 40)) is None
        assert sent == [] and ma._load(ma.STATE_KEY, {}).get("digest") is None

    def test_off_switch(self, market, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "map_alerts_enabled", False)
        assert ma.evening_due(at(AS_OF, 16, 40)) is False


class TestVolShift:
    def stock(self, sym, vol, usual=5.0):
        rows = [{"level_pct": lvl, "price": 1.0, "odds": [0.1] * 4, "usual": [0.05] * 4}
                for lvl in (30.0, 20.0, 10.0, 5.0, -5.0, -10.0, -20.0, -30.0)]
        return {"symbol": sym, "map": {"vol_pct": vol, "vol_usual_pct": usual, "rows": rows, "horizons": [1, 5, 10, 20]}}

    def test_state_changes_and_quiet_week(self):
        state, d0 = {}, date(2026, 11, 2)
        assert [x["state"] for x in ma.vol_shifts([self.stock("A", 8.0)], state, d0)] == ["high"]
        assert ma.vol_shifts([self.stock("A", 8.0)], state, d0 + timedelta(days=1)) == []      # still high
        assert ma.vol_shifts([self.stock("A", 5.0)], state, d0 + timedelta(days=2)) == []      # back to normal
        assert ma.vol_shifts([self.stock("A", 8.0)], state, d0 + timedelta(days=3)) == []      # within the week
        assert ma.vol_shifts([self.stock("A", 5.0)], state, d0 + timedelta(days=8)) == []
        assert len(ma.vol_shifts([self.stock("A", 8.0)], state, d0 + timedelta(days=9))) == 1
        assert [x["state"] for x in ma.vol_shifts([self.stock("B", 3.0)], state, d0)] == ["low"]

    @pytest.mark.parametrize("vol,expect", [(7.5, "high"), (7.49, None), (5.0 / 1.5, "low"), (3.4, None)])
    def test_threshold(self, vol, expect):
        got = ma.vol_shifts([self.stock("A", vol)], {}, date(2026, 11, 2))
        assert (got[0]["state"] if got else None) == expect

    def test_text(self):
        x = ma.vol_shifts([self.stock("AVGO", 8.0)], {}, date(2026, 11, 2))[0]
        tg, sms = ma.format_vol_shift(x)
        assert "AVGO is moving 1.6x its usual" in tg and "widened" in tg and "+10% within 20 sessions 10% (usual 5%)" in tg
        assert len(sms) == 1 and len(sms[0]) <= ma.SMS_MAX


# ---------------------------------------------------------------- big open

def open_map(up, down, close_up=0.07, close_down=0.04, verdict="about as accurate as its usual odds"):
    return {"symbol": "CLSK", "data_ok": True, "in_progress": True, "last_close": 6.21,
            "big_day": {"up": close_up, "down": close_down, "usual_up": 0.073, "usual_down": 0.039},
            "today": {"open": 6.48, "gap_pct": 4.35, "up": up, "down": down},
            "calibration": {"big_day": {"open_verdict": verdict}}}


class TestBigOpen:
    def test_alert_when_twice_usual(self):
        tg, sms = ma.open_alert(open_map(0.15, 0.005))
        assert "CLSK opened +4.3% at $6.48" in tg and "closing 10%+ up today (at or above $6.83): 15%" in tg
        assert "against 7% at the previous close (usual 7%)" in tg and "about as accurate as its usual odds" in tg
        assert len(sms[0]) <= ma.SMS_MAX and sms[0].startswith("MSE CLSK opened +4.3%")

    @pytest.mark.parametrize("up,close_up,fires", [(0.14, 0.073, False), (0.146, 0.073, True), (0.04, 0.01, False)])
    def test_threshold_and_minimum(self, up, close_up, fires):
        assert (ma.open_alert(open_map(up, 0.0, close_up=close_up)) is not None) is fires

    def test_a_flat_open_in_a_volatile_stretch_is_not_a_big_open(self):
        # moving a lot: the odds from the close are already well above usual, and a flat open leaves them there
        assert ma.open_alert(open_map(0.16, 0.08, close_up=0.155, close_down=0.08)) is None

    def test_down_side(self):
        tg, _ = ma.open_alert(open_map(0.01, 0.12))
        assert "closing 10%+ down today (at or below $5.59): 12%" in tg

    def test_once_per_stock_per_day_and_waits_for_the_open(self, market, sent, monkeypatch):
        answers = {"AAA": [{"data_ok": True, "in_progress": True, "today": None}], "BBB": []}
        m = open_map(0.2, 0.0)

        def fake(sym, now=None, background=False):
            assert background is True
            if answers.get(sym):
                return answers[sym].pop(0)
            return {**m, "symbol": sym}

        monkeypatch.setattr(pm, "probability_map", fake)
        day = AS_OF
        assert ma.open_tick(at(day, 9, 50)) == ["BBB"]                 # AAA's open not in yet
        assert ma.open_tick(at(day, 9, 55)) == ["AAA"]
        assert ma.open_tick(at(day, 10, 0)) == []
        assert [k for k, _, _ in sent] == ["open", "open"]

    @pytest.mark.parametrize("hh,mm,due", [(9, 44, False), (9, 45, True), (10, 29, True), (10, 30, False)])
    def test_window(self, hh, mm, due):
        assert ma.open_due(at(date(2026, 11, 19), hh, mm)) is due


# ---------------------------------------------------------------- price levels

class TestLevels:
    @pytest.fixture
    def priced(self, monkeypatch):
        monkeypatch.setattr(ma, "_last_price", lambda sym, now=None: 6.21)

    def test_add_list_remove(self, priced):
        up = ma.add_level("clsk", 6.52)
        dn = ma.add_level("CLSK", "5.90")
        assert up["ok"] and up["level"]["side"] == "above" and dn["level"]["side"] == "below"
        assert ma.add_level("CLSK", 6.52)["note"] == "Already set."
        assert [(x["symbol"], x["price"]) for x in ma.list_levels()["levels"]] == [("CLSK", 6.52), ("CLSK", 5.9)]
        assert ma.remove_level("CLSK", 6.52) == {"ok": True}
        assert ma.remove_level("CLSK", 6.52)["ok"] is False
        assert ma.remove_level("CLSK", 5.9) == {"ok": True} and ma.list_levels()["levels"] == []

    @pytest.mark.parametrize("sym,price,note", [
        ("<x>", 6.5, "Not a stock symbol."), ("CLSK", "abc", "Not a price."), ("CLSK", -1, "Not a price."),
        ("CLSK", float("inf"), "Not a price."), ("CLSK", 30.0, "too far"), ("CLSK", 1.0, "too far"),
        ("CLSK", 6.2101, "right at"),
    ])
    def test_rejected(self, priced, sym, price, note):
        out = ma.add_level(sym, price)
        assert out["ok"] is False and note in out["note"]

    def test_no_price(self, monkeypatch):
        monkeypatch.setattr(ma, "_last_price", lambda sym, now=None: None)
        assert ma.add_level("ZZZZ", 5.0)["note"] == "No recent price for ZZZZ."

    def test_limits(self, priced, monkeypatch):
        monkeypatch.setattr(ma, "MAX_LEVELS_PER_STOCK", 2)
        ma.add_level("CLSK", 6.5)
        ma.add_level("CLSK", 6.6)
        assert "already has 2" in ma.add_level("CLSK", 6.7)["note"]
        monkeypatch.setattr(ma, "MAX_LEVELS", 3)
        ma.add_level("RIOT", 7.0)
        assert "already 3" in ma.add_level("MARA", 6.5)["note"]

    @pytest.fixture
    def session(self, monkeypatch, priced):
        day = date(2026, 11, 19)
        idx = pd.date_range(at(day, 9, 30), periods=20, freq="1min")
        highs = np.r_[np.full(10, 6.45), 6.53, np.full(9, 6.50)]
        lows = np.r_[np.full(15, 6.30), 5.88, np.full(4, 6.0)]
        bars = pd.DataFrame({"open": 6.4, "high": highs, "low": lows, "close": 6.4, "volume": 100}, index=idx)
        calls = []
        monkeypatch.setattr(alert_rules, "market_open", lambda now=None: True)
        monkeypatch.setattr(ma, "session_bars", lambda syms, now: calls.append(syms) or {"CLSK": bars})
        monkeypatch.setattr(ma, "level_context", lambda sym, price, today, side: {
            "pct": (price / 6.21 - 1) * 100, "within": {1: 0.42, 5: 0.69, 10: 0.78, 20: 0.84},
            "held5": 0.49, "touches": 300, "close": 6.21, "as_of": date(2026, 11, 18), "applies": True})
        return day, calls

    def test_hits_are_alerted_once(self, session, sent):
        day, calls = session
        before = at(day, 9, 0)
        ma.add_level("CLSK", 6.52, now=before)
        ma.add_level("CLSK", 5.90, now=before)
        ma.add_level("CLSK", 6.60, now=before)                           # not reached
        out = ma.check_levels(at(day, 10, 0))
        assert out == ["CLSK $6.52", "CLSK $5.90"]
        _, tg, sms = sent[0]
        assert "CLSK traded at $6.52 at 9:40 AM (your level; high so far $6.53)" in tg
        assert "gave it 42% for the next session and 69% within 5 sessions" in tg and "49% were still at or above" in tg
        assert len(sms[0]) <= ma.SMS_MAX and sms[0].startswith("MSE CLSK hit $6.52 9:40 AM")
        assert "at or below" in sent[1][1] and "low so far $5.88" in sent[1][1]
        assert ma.check_levels(at(day, 10, 1)) == [] and len(sent) == 2      # hit levels are not alerted again
        waiting = [x for x in ma.list_levels()["levels"] if not x["hit"]]
        assert [x["price"] for x in waiting] == [6.6]

    def test_closed_market_fetches_nothing(self, session, monkeypatch):
        day, calls = session
        ma.add_level("CLSK", 6.52, now=at(day, 9, 0))
        monkeypatch.setattr(alert_rules, "market_open", lambda now=None: False)
        assert ma.check_levels(at(day, 17, 0)) == [] and calls == []

    def test_no_levels_fetches_nothing(self, session):
        day, calls = session
        assert ma.check_levels(at(day, 10, 0)) == [] and calls == []

    def test_the_thread_survives_a_failed_check(self, monkeypatch):
        stop = threading.Event()
        ticks = []

        def boom(now=None):
            ticks.append(1)
            if len(ticks) >= 2:
                stop.set()
            raise RuntimeError("alpaca down")

        monkeypatch.setattr(ma, "LEVEL_START_DELAY", 0)
        monkeypatch.setattr(ma, "LEVEL_TICK", 0.01)
        monkeypatch.setattr(ma, "check_levels", boom)
        ma.run_levels(stop)
        assert len(ticks) == 2


# ---------------------------------------------------------------- delivery

class Config:
    def __init__(self, **kw):
        self.sms_to = kw.get("sms_to", "5551234507")
        self.sms_consent = kw.get("sms_consent", True)
        self.auto_alerts_enabled = kw.get("auto", True)
        self.sms_method = kw.get("method", "email_gateway")
        self.sms_carrier = "tmobile"


class TestDelivery:
    @pytest.fixture
    def wires(self, monkeypatch):
        tg, sms = [], []
        monkeypatch.setattr(dispatcher, "_send_telegram", lambda kind, body: tg.append((kind, body)) or True)
        monkeypatch.setattr(dispatcher, "_send_text_sms", lambda config, body: sms.append(body) or True)
        monkeypatch.setattr(dispatcher, "load_config", lambda: Config())
        return tg, sms

    def test_both_channels(self, wires):
        tg, sms = wires
        out = dispatcher.dispatch_map_alert("level", "long text", ["a" * 200, "b", "c", "d"])
        assert out == {"telegram": True, "sms": 3}
        assert tg == [("map_level", "long text")] and sms == ["a" * 155, "b", "c"]

    def test_switches(self, wires, monkeypatch):
        tg, sms = wires
        from config.settings import settings
        monkeypatch.setattr(settings, "map_alerts_enabled", False)
        assert dispatcher.dispatch_map_alert("digest", "x", ["y"]) == {"telegram": False, "sms": 0}
        monkeypatch.setattr(settings, "map_alerts_enabled", True)
        monkeypatch.setattr(dispatcher, "load_config", lambda: Config(auto=False))
        assert dispatcher.dispatch_map_alert("digest", "x", ["y"]) == {"telegram": False, "sms": 0}
        monkeypatch.setattr(dispatcher, "load_config", lambda: Config(sms_consent=False))
        assert dispatcher.dispatch_map_alert("digest", "x", ["y"]) == {"telegram": True, "sms": 0}
        assert tg == [("map_digest", "x")] and sms == []

    def test_repeated_texts_are_dropped(self, wires, monkeypatch):
        tg, sms = wires
        seen = {}
        monkeypatch.setattr(dispatcher, "_recent_sms_fingerprints", lambda: seen)
        monkeypatch.setattr(dispatcher, "_record_sms_fingerprint", lambda fp: seen.__setitem__(fp, "now"))
        dispatcher.dispatch_map_alert("level", "t", ["same"])
        dispatcher.dispatch_map_alert("level", "t", ["same"])
        assert sms == ["same"]

    def test_a_failing_text_is_not_raised(self, wires, monkeypatch):
        def boom(config, body):
            raise OSError("network")
        monkeypatch.setattr(dispatcher, "_send_text_sms", boom)
        assert dispatcher.dispatch_map_alert("level", "t", ["x"]) == {"telegram": True, "sms": 0}


class TestBrevo:
    @pytest.fixture
    def keyed(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-SECRET-1234")
        monkeypatch.setattr(settings, "brevo_sender_email", "me@example.com")

    def fake_post(self, monkeypatch, status, text=""):
        calls = []

        class Resp:
            status_code = status

        Resp.text = text

        def post(url, headers=None, json=None, timeout=None):
            calls.append((url, headers, json))
            return Resp()

        monkeypatch.setattr(dispatcher.http_requests, "post", post)
        return calls

    def test_gateway_text_goes_over_https(self, keyed, monkeypatch):
        calls = self.fake_post(monkeypatch, 201)
        assert dispatcher._send_text_sms(Config(sms_to="+1 (555) 123-4507"), "hello") is True
        url, headers, body = calls[0]
        assert url == "https://api.brevo.com/v3/smtp/email" and headers["api-key"] == "xkeysib-SECRET-1234"
        assert body["to"] == [{"email": "5551234507@tmomail.net"}] and body["textContent"] == "hello"
        assert body["sender"]["email"] == "me@example.com"

    def test_refusal_is_logged_without_the_key(self, keyed, monkeypatch, mse_logs):
        self.fake_post(monkeypatch, 401, "key xkeysib-SECRET-1234 is not valid")
        assert dispatcher._send_text_sms(Config(), "hello") is False
        assert "HTTP 401" in mse_logs.text and "xkeysib-SECRET-1234" not in mse_logs.text and "[key]" in mse_logs.text

    def test_without_a_key_it_uses_smtp_as_before(self, monkeypatch):
        calls = self.fake_post(monkeypatch, 201)
        assert dispatcher._send_text_sms(Config(), "hello") is False      # no SMTP login either
        assert calls == []

    def test_no_sender_no_send(self, keyed, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "brevo_sender_email", "")
        calls = self.fake_post(monkeypatch, 201)
        assert dispatcher._send_text_sms(Config(), "hello") is False and calls == []


# ---------------------------------------------------------------- routes and wiring

class TestRoutes:
    @pytest.fixture
    def api(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        monkeypatch.setattr(ma, "_last_price", lambda sym, now=None: 6.21)
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_locked_without_a_settings_key(self, api):
        r = api.post("/alerts/levels?symbol=CLSK&price=6.52")
        assert r.status_code == 403 and "SETTINGS_KEY" in r.json()["detail"]
        assert api.delete("/alerts/levels?symbol=CLSK&price=6.52").status_code == 403
        assert api.get("/alerts/levels").json() == {"ok": True, "levels": []}

    def test_with_the_key(self, api, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "settings_key", "a-long-test-settings-key")
        hdr = {"X-Settings-Key": "a-long-test-settings-key"}
        assert api.post("/alerts/levels?symbol=CLSK&price=6.52", headers={"X-Settings-Key": "wrong"}).status_code == 403
        r = api.post("/alerts/levels?symbol=CLSK&price=6.52", headers=hdr)
        assert r.status_code == 200 and r.json()["level"]["side"] == "above"
        assert api.get("/alerts/levels").json()["levels"][0]["price"] == 6.52
        assert api.delete("/alerts/levels?symbol=CLSK&price=6.52", headers=hdr).json() == {"ok": True}
        assert api.post("/alerts/levels?symbol=CLSK&price=0", headers=hdr).status_code == 422


class TestWiring:
    def test_evening_after_the_map_record(self):
        from src import main
        src = inspect.getsource(main._refresh_loop)
        assert src.index("Map record failed") < src.index("map_alerts.evening_due()")
        block = src[src.index("map_alerts.evening_due()"):src.index("Map digest failed")]
        assert 'heavy.run("map digest", map_alerts.evening)' in block and 'heavy.should_skip("map digest")' in block

    def test_big_open_in_the_intraday_loop(self):
        from src import main
        src = inspect.getsource(main._intraday_scan_loop)
        block = src[src.index("map_alerts.open_due()"):src.index("Big-open alert check failed")]
        assert 'heavy.run("open odds alerts", map_alerts.open_tick)' in block

    def test_levels_thread_started(self):
        from src import main
        assert "map_alerts.run_levels" in inspect.getsource(main.lifespan)

    def test_watchlist(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "map_alert_symbols", " iren, CLSK ,<bad>, ")
        assert ma.watchlist() == ["CLSK", "RIOT", "MARA", "NVDA", "AVGO", "TSLA", "IREN"]


class TestContention:
    """Page requests against the 9:45 background check for the one
    calculation slot."""

    @pytest.fixture
    def session_day(self, monkeypatch):
        from src.data import fmp_client
        day = DAYS[-1]
        monkeypatch.setattr(client, "get_multi_bars",
                            lambda symbols, days=200, **kw: {s: BARS["AAA"].copy() for s in symbols})
        monkeypatch.setattr(fmp_client, "get_symbol_next_earnings", lambda s, today=None: (False, None))
        monkeypatch.setattr(pm, "calibrate", lambda p, sessions=0: None)
        monkeypatch.setattr(alert_rules, "trading_day", lambda d: True)
        pm._cache.clear()
        yield at(day, 9, 50)
        pm._cache.clear()

    def test_a_page_request_goes_ahead_of_the_background_loop(self, session_day, monkeypatch, sent):
        now = session_day
        monkeypatch.setattr(ma, "watchlist", lambda: ["AAA", "BBB", "CCC"])
        real_build = pm.build
        in_first, release = threading.Event(), threading.Event()
        order = []

        def build(*a, **k):
            name = threading.current_thread().name
            order.append(name)
            if name == "background" and not in_first.is_set():
                in_first.set()
                assert release.wait(5)
            return real_build(*a, **k)

        monkeypatch.setattr(pm, "build", build)
        bg_result = []
        bg = threading.Thread(target=lambda: bg_result.append(ma.open_tick(now)), name="background")
        bg.start()
        assert in_first.wait(5)                               # the loop is building AAA
        page_out = []
        page = threading.Thread(target=lambda: page_out.append(pm.probability_map("PAGE", now=now)), name="page")
        page.start()
        for _ in range(200):                                  # until the page request is waiting for the slot
            if pm._page_waiting:
                break
            threading.Event().wait(0.01)
        assert pm._page_waiting == 1
        release.set()
        page.join(10)
        bg.join(10)
        assert page_out[0]["data_ok"]
        assert order[:2] == ["background", "page"]            # the page went before the rest of the loop
        # (the loop either skipped a stock while the page waited or waited behind it; both are fine)
        ma.open_tick(now)                                     # any stock left over is picked up next pass
        assert ma._load(ma.STATE_KEY, {})["open"][str(now.date())] == ["AAA", "BBB", "CCC"]

    def test_two_overlapping_page_requests_both_get_maps(self, session_day):
        now = session_day
        out = []
        threads = [threading.Thread(target=lambda s=s: out.append(pm.probability_map(s, now=now))) for s in ("X1", "X2")]
        for th in threads:
            th.start()
        for th in threads:
            th.join(20)
        assert len(out) == 2 and all(o["data_ok"] for o in out)

    def test_background_does_not_wait_on_a_page_build_of_the_same_stock(self, session_day):
        pm._inflight["CLSK"] = threading.Event()              # a page request is building CLSK
        try:
            out = pm.probability_map("CLSK", background=True)
        finally:
            pm._inflight.pop("CLSK", None)
        assert out["retry"] is True and out["note"] == pm.BUSY

    def test_a_page_request_builds_it_itself_if_the_shared_build_gave_up(self, session_day):
        ev = threading.Event()
        pm._inflight["SAME"] = ev
        th = threading.Thread(target=lambda: (threading.Event().wait(0.2), pm._inflight.pop("SAME", None), ev.set()))
        th.start()                                            # the other build ends without a result
        out = pm.probability_map("SAME", now=session_day)
        th.join()
        assert out["data_ok"]

    def test_empty_watchlist(self, session_day, monkeypatch):
        calls = []
        monkeypatch.setattr(ma, "watchlist", lambda: [])
        monkeypatch.setattr(pm, "probability_map", lambda *a, **k: calls.append(a) or {})
        assert ma.open_tick(session_day) == [] and calls == []

    def test_a_busy_answer_is_logged(self, session_day, monkeypatch, mse_logs):
        import logging
        logging.getLogger("mse.probability_map").addHandler(mse_logs.handler)
        monkeypatch.setattr(pm, "BUILD_WAIT", 0.2)
        assert pm._cpu_slot.acquire(timeout=1)
        try:
            out = pm.probability_map("BUSY1", now=session_day)
        finally:
            pm._cpu_slot.release()
            logging.getLogger("mse.probability_map").removeHandler(mse_logs.handler)
        assert out["retry"] is True
        assert "Probability map for BUSY1 not built: waited 0.2s for the calculation slot" in mse_logs.text

    def test_a_page_request_waits_at_most_the_build_limit_in_all(self, session_day, monkeypatch):
        import time as _time
        monkeypatch.setattr(pm, "BUILD_WAIT", 0.3)
        pm._inflight["SLOW"] = threading.Event()              # never finishes
        assert pm._cpu_slot.acquire(timeout=1)
        t0 = _time.time()
        try:
            th = threading.Thread(target=lambda: (threading.Event().wait(0.1), pm._inflight.pop("SLOW", None)))
            th.start()                                        # the shared build vanishes; the page tries itself
            out = pm.probability_map("SLOW", now=session_day)
            th.join()
        finally:
            pm._cpu_slot.release()
            pm._inflight.pop("SLOW", None)
        assert out["retry"] is True and _time.time() - t0 < 0.3 + 0.5


class TestReviewFixes:
    """Cases from the pre-push review, with the real odds code where it matters."""

    def test_trades_before_a_level_was_set_do_not_count(self, monkeypatch, sent):
        day = date(2026, 11, 19)
        idx = pd.date_range(at(day, 9, 30), periods=300, freq="1min")
        high = np.full(300, 6.30)
        high[30] = 6.60                                       # 10:00, before the level is set
        high[280] = 6.55                                      # 14:10, after
        bars = pd.DataFrame({"open": 6.3, "high": high, "low": 6.2, "close": 6.3, "volume": 1}, index=idx)
        monkeypatch.setattr(alert_rules, "market_open", lambda now=None: True)
        monkeypatch.setattr(ma, "session_bars", lambda syms, now: {"CLSK": bars[bars.index <= now]})   # up to now
        monkeypatch.setattr(ma, "_last_price", lambda sym, now=None: 6.30)
        monkeypatch.setattr(ma, "level_context", lambda *a: None)
        ma.add_level("CLSK", 6.52, now=at(day, 14, 0))
        assert ma.check_levels(at(day, 14, 5)) == []          # the 10:00 trade does not count
        assert ma.check_levels(at(day, 14, 20)) == ["CLSK $6.52"]
        assert "at 2:10 PM" in sent[0][1]

    def test_the_side_comes_from_the_latest_intraday_price(self, monkeypatch):
        day = date(2026, 11, 19)
        idx = pd.date_range(at(day, 9, 30), periods=5, freq="1min")
        bars = pd.DataFrame({"open": 6.6, "high": 6.6, "low": 6.6, "close": [6.40, 6.5, 6.55, 6.6, 6.61]}, index=idx)
        monkeypatch.setattr(alert_rules, "market_open", lambda now=None: True)
        monkeypatch.setattr(ma, "session_bars", lambda syms, now: {"CLSK": bars})
        monkeypatch.setattr(client, "get_multi_bars", lambda *a, **k: {"CLSK": BARS["AAA"]})   # stale daily close
        assert ma._last_price("CLSK", at(day, 9, 36)) == 6.61
        assert ma.add_level("CLSK", 6.52, now=at(day, 9, 36))["level"]["side"] == "below"

    def test_odds_only_when_the_level_is_on_the_side_it_is_reached_from(self, monkeypatch):
        monkeypatch.setattr(client, "get_multi_bars", lambda *a, **k: {"AAA": BARS["AAA"]})
        today = DAYS[-1] + timedelta(days=1)
        close = float(pm.clean_bars(BARS["AAA"])["close"].iloc[-1])
        level = round(close * 1.02, 4)
        above = ma.level_context("AAA", level, today, "above")
        below = ma.level_context("AAA", level, today, "below")   # a pullback from higher to a level above the close
        assert above["applies"] and above["within"][1] > 0 and above["pct"] == pytest.approx(2.0, abs=0.01)
        assert below == {"close": close, "as_of": DAYS[-1], "pct": pytest.approx(2.0, abs=0.01), "applies": False}
        tg, sms = ma.format_level_hit("AAA", {"price": level, "side": "below"}, at(today, 11, 0), level * 0.99, below)
        assert "do not apply" in tg and "%" not in tg.split("do not apply")[1].split("IEX")[0]
        assert "were still" not in tg and len(sms[0]) <= ma.SMS_MAX

    def test_redis_writes_failing_send_the_digest_once(self, market, sent, monkeypatch):
        class ReadOnly:
            def get(self, key):
                return None

            def set(self, key, value, ex=None):
                raise ConnectionError("data cap reached")

        monkeypatch.setattr(ma, "_redis", lambda: ReadOnly())
        for minute in (40, 50, 0, 10):
            hh = 16 if minute >= 40 else 17
            if ma.evening_due(at(AS_OF, hh, minute)):
                ma.evening(at(AS_OF, hh, minute))
        assert [k for k, _, _ in sent].count("digest") == 1

    def test_redis_writes_failing_send_big_open_once(self, market, sent, monkeypatch):
        class ReadOnly:
            def get(self, key):
                return None

            def set(self, key, value, ex=None):
                raise ConnectionError("data cap reached")

        monkeypatch.setattr(ma, "_redis", lambda: ReadOnly())
        monkeypatch.setattr(pm, "probability_map", lambda sym, now=None, background=False: {**open_map(0.3, 0.0), "symbol": sym})
        for mm in (50, 55, 0, 5):
            ma.open_tick(at(AS_OF, 9 if mm >= 50 else 10, mm))
        assert [k for k, _, _ in sent] == ["open", "open"]                # AAA and BBB, once each

    def test_the_digest_is_not_sent_after_the_open(self, market, sent):
        late = at(AS_OF + timedelta(days=1), 9, 40) if AS_OF.weekday() < 4 else at(AS_OF + timedelta(days=3), 9, 40)
        assert ma.evening(late) is None and sent == []

    def test_a_half_day_ends_at_its_close(self, monkeypatch):
        day = date(2026, 11, 27)
        monkeypatch.setattr(ma, "session_close", lambda d: datetime(2026, 11, 27, 13, 0).time())
        monkeypatch.setattr(alert_rules, "market_open", lambda now=None: True)
        called = []
        monkeypatch.setattr(ma, "session_bars", lambda syms, now: called.append(1) or {})
        ma._save(ma.LEVELS_KEY, {"CLSK": [{"price": 6.5, "side": "above", "ref": 6.2, "added": "2026-11-26T10:00-05:00", "hit": None}]})
        assert ma.check_levels(at(day, 13, 30)) == [] and called == []

    def test_session_close_reads_alpacas_calendar(self, monkeypatch):
        from src.data import client as dc

        class Day:
            close = datetime(2026, 11, 27, 13, 0)

        class Trading:
            def get_calendar(self, req):
                return [Day()]

        monkeypatch.setattr(dc, "_get_trading_client", lambda: Trading())
        assert REAL_SESSION_CLOSE(date(2026, 11, 27)).strftime("%H:%M") == "13:00"
        monkeypatch.setattr(dc, "_get_trading_client", lambda: (_ for _ in ()).throw(RuntimeError("down")))
        assert REAL_SESSION_CLOSE(date(2026, 11, 30)).strftime("%H:%M") == "16:00"

    def test_session_bars_stop_at_the_close(self, monkeypatch):
        from src.data import client as dc
        day = date(2026, 11, 27)
        idx = pd.MultiIndex.from_product([["CLSK"], pd.date_range(at(day, 12, 58), periods=5, freq="1min")],
                                         names=["symbol", "timestamp"])
        df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1}, index=idx)

        class Data:
            def get_stock_bars(self, req):
                return type("R", (), {"df": df})()

        monkeypatch.setattr(dc, "_get_data_client", lambda: Data())
        monkeypatch.setattr(ma, "session_close", lambda d: datetime(2026, 11, 27, 13, 0).time())
        got = ma.session_bars(["CLSK"], at(day, 13, 30))["CLSK"]
        assert [t.strftime("%H:%M") for t in got.index] == ["12:58", "12:59"]
