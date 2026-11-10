"""Spike and reversal detectors (src/scanner/spike_reversal.py). No network."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.scanner import spike_reversal as sr

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 10, 11, 0, tzinfo=ET)      # Tuesday, mid-session


def session(rows, start=datetime(2026, 11, 10, 9, 30, tzinfo=ET)):
    """5-minute bars from (open, high, low, close, volume) rows."""
    idx = pd.DatetimeIndex([start + timedelta(minutes=5 * i) for i in range(len(rows))])
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)


def daily(closes, volumes=None, highs=None, lows=None, end=date(2026, 11, 10)):
    n = len(closes)
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    idx = pd.DatetimeIndex([pd.Timestamp(x, tz="UTC") + pd.Timedelta(hours=5) for x in reversed(days)])
    return pd.DataFrame({
        "open": closes, "high": highs or [c * 1.01 for c in closes],
        "low": lows or [c * 0.99 for c in closes], "close": closes,
        "volume": volumes or [1_000_000] * n,
    }, index=idx)


FLAT_BAR = (100.0, 100.2, 99.8, 100.0, 10_000)


# ------------------------------------------------------------ volume ignition

class TestVolumeIgnition:
    SLOTS = {"09:30": 10_000, "09:35": 10_000, "09:40": 10_000}

    def test_up_through_yesterdays_high(self):
        sdf = session([FLAT_BAR, FLAT_BAR, (100.0, 102.5, 100.0, 102.4, 90_000)])
        e = sr.detect_volume_ignition("X", sdf, self.SLOTS, prior_high=101.0, prior_low=98.0)
        assert e["kind"] == "volume_ignition" and e["direction"] == "up"
        assert e["multiple"] == 9.0 and e["price"] == 102.4

    def test_down_through_yesterdays_low(self):
        sdf = session([FLAT_BAR, FLAT_BAR, (100.0, 100.0, 97.0, 97.2, 80_000)])
        e = sr.detect_volume_ignition("X", sdf, self.SLOTS, prior_high=101.0, prior_low=98.0)
        assert e["direction"] == "down"

    def test_heavy_volume_inside_yesterdays_range_is_not_ignition(self):
        sdf = session([FLAT_BAR, FLAT_BAR, (100.0, 100.9, 100.0, 100.8, 90_000)])
        assert sr.detect_volume_ignition("X", sdf, self.SLOTS, 101.0, 98.0) is None

    def test_breakout_on_ordinary_volume_is_not_ignition(self):
        sdf = session([FLAT_BAR, FLAT_BAR, (100.0, 102.5, 100.0, 102.4, 70_000)])   # 7x < 8x
        assert sr.detect_volume_ignition("X", sdf, self.SLOTS, 101.0, 98.0) is None

    def test_up_volume_but_bar_closed_red(self):
        sdf = session([FLAT_BAR, FLAT_BAR, (103.0, 103.5, 101.5, 101.6, 90_000)])
        assert sr.detect_volume_ignition("X", sdf, self.SLOTS, 101.0, 98.0) is None

    def test_no_baseline_for_the_slot(self):
        sdf = session([FLAT_BAR, FLAT_BAR, (100.0, 102.5, 100.0, 102.4, 90_000)])
        assert sr.detect_volume_ignition("X", sdf, {"09:40": 200}, 101.0, 98.0) is None
        assert sr.detect_volume_ignition("X", sdf, {}, 101.0, 98.0) is None
        assert sr.detect_volume_ignition("X", sdf, None, 101.0, 98.0) is None

    def test_empty_and_short_input(self):
        assert sr.detect_volume_ignition("X", None, self.SLOTS, 101.0, 98.0) is None
        assert sr.detect_volume_ignition("X", session([FLAT_BAR]), self.SLOTS, 101.0, 98.0) is None


class TestVolumeProfile:
    def _history(self, sessions, vol=1000):
        frames = []
        d = date(2026, 11, 9)
        while len(frames) < sessions:
            if d.weekday() < 5:
                start = datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)
                frames.append(session([(1, 1, 1, 1, vol + 10 * i) for i in range(3)], start))
            d -= timedelta(days=1)
        return pd.concat(frames).sort_index()

    def test_median_per_slot_excluding_today(self):
        hist = self._history(6)
        today_bars = session([(1, 1, 1, 1, 999_999)] * 3)        # must not count
        prof = sr.build_volume_profile({"X": pd.concat([hist, today_bars])}, NOW.date())
        assert prof["X"] == {"09:30": 1000.0, "09:35": 1010.0, "09:40": 1020.0}

    def test_too_few_sessions_gives_no_profile(self):
        assert sr.build_volume_profile({"X": self._history(3)}, NOW.date()) == {}

    def test_premarket_bars_and_empty_frames_are_ignored(self):
        hist = self._history(6)
        pre = session([(1, 1, 1, 1, 5_000_000)],
                      start=datetime(2026, 11, 9, 8, 0, tzinfo=ET))
        prof = sr.build_volume_profile({"X": pd.concat([hist, pre]).sort_index(),
                                        "Y": pd.DataFrame()}, NOW.date())
        assert "08:00" not in prof["X"] and "Y" not in prof

    def test_naive_utc_index_is_handled(self):
        hist = self._history(6)
        hist.index = hist.index.tz_convert("UTC").tz_localize(None)
        assert "09:30" in sr.build_volume_profile({"X": hist}, NOW.date())["X"]


# --------------------------------------------------------------- failed break

class TestFailedBreak:
    def test_failed_breakout(self):
        sdf = session([FLAT_BAR, (100.0, 101.6, 100.0, 101.5, 1), (101.5, 101.6, 100.4, 100.5, 1)])
        e = sr.detect_failed_break("X", sdf, prior_high=101.0, prior_low=98.0)
        assert e["kind"] == "failed_breakout" and e["direction"] == "down" and e["level"] == 101.0

    def test_failed_breakdown(self):
        sdf = session([FLAT_BAR, (100.0, 100.0, 97.4, 97.5, 1), (97.5, 98.6, 97.5, 98.5, 1)])
        e = sr.detect_failed_break("X", sdf, prior_high=101.0, prior_low=98.0)
        assert e["kind"] == "failed_breakdown" and e["direction"] == "up"

    def test_breakout_still_holding_is_not_a_failure(self):
        sdf = session([FLAT_BAR, (100.0, 101.6, 100.0, 101.5, 1), (101.5, 102.0, 101.4, 101.8, 1)])
        assert sr.detect_failed_break("X", sdf, 101.0, 98.0) is None

    def test_wick_above_without_a_close_is_not_a_break(self):
        sdf = session([FLAT_BAR, (100.0, 101.8, 100.0, 100.6, 1), (100.6, 100.7, 100.2, 100.3, 1)])
        assert sr.detect_failed_break("X", sdf, 101.0, 98.0) is None

    def test_gap_open_above_the_level_is_ignored(self):
        sdf = session([(102.0, 102.5, 101.8, 102.2, 1), (102.2, 102.3, 101.5, 101.6, 1),
                       (101.6, 101.7, 100.4, 100.5, 1)])
        assert sr.detect_failed_break("X", sdf, 101.0, 98.0) is None

    def test_old_break_outside_the_lookback(self):
        rows = [FLAT_BAR, (100.0, 101.6, 100.0, 101.5, 1)] + [FLAT_BAR] * 12
        assert sr.detect_failed_break("X", session(rows), 101.0, 98.0) is None

    def test_barely_back_inside_does_not_count(self):
        sdf = session([FLAT_BAR, (100.0, 101.6, 100.0, 101.5, 1), (101.5, 101.5, 100.9, 100.95, 1)])
        assert sr.detect_failed_break("X", sdf, 101.0, 98.0) is None

    def test_a_marginal_break_does_not_count(self):
        # closed 0.1% above the level, then back: routine noise, not a trap
        sdf = session([FLAT_BAR, (100.0, 101.2, 100.0, 101.1, 1), (101.1, 101.1, 100.4, 100.5, 1)])
        assert sr.detect_failed_break("X", sdf, 101.0, 98.0) is None
        sdf = session([FLAT_BAR, (100.0, 100.0, 97.9, 97.95, 1), (97.95, 98.6, 97.9, 98.5, 1)])
        assert sr.detect_failed_break("X", sdf, 101.0, 98.0) is None

    def test_bad_input(self):
        assert sr.detect_failed_break("X", None, 101.0, 98.0) is None
        assert sr.detect_failed_break("X", session([FLAT_BAR] * 2), 101.0, 98.0) is None
        assert sr.detect_failed_break("X", session([FLAT_BAR] * 5), 0.0, 0.0) is None


# -------------------------------------------------- exhaustion / capitulation

class TestExhaustion:
    def test_exhaustion_top(self):
        closes = [10.0] * 30 + [10.5, 11.5, 12.5, 13.5, 13.0]
        d = daily(closes, volumes=[1_000_000] * 34 + [4_000_000],
                  highs=[c * 1.01 for c in closes[:-1]] + [15.0],
                  lows=[c * 0.99 for c in closes[:-1]] + [12.8])
        e = sr.detect_exhaustion("X", d)
        assert e["kind"] == "exhaustion_top" and e["direction"] == "down" and e["multiple"] == 4.0

    def test_capitulation_low(self):
        closes = [20.0] * 30 + [19.0, 18.0, 17.0, 16.0, 16.4]
        d = daily(closes, volumes=[1_000_000] * 34 + [5_000_000],
                  highs=[c * 1.01 for c in closes[:-1]] + [16.6],
                  lows=[c * 0.99 for c in closes[:-1]] + [14.5])
        e = sr.detect_exhaustion("X", d)
        assert e["kind"] == "capitulation_low" and e["direction"] == "up"

    def test_strong_close_after_a_run_is_not_exhaustion(self):
        closes = [10.0] * 30 + [10.5, 11.5, 12.5, 13.5, 14.9]
        d = daily(closes, volumes=[1_000_000] * 34 + [4_000_000],
                  highs=[c * 1.01 for c in closes[:-1]] + [15.0],
                  lows=[c * 0.99 for c in closes[:-1]] + [13.4])
        assert sr.detect_exhaustion("X", d) is None

    def test_needs_heavy_volume(self):
        closes = [10.0] * 30 + [10.5, 11.5, 12.5, 13.5, 13.0]
        d = daily(closes, highs=[c * 1.01 for c in closes[:-1]] + [15.0],
                  lows=[c * 0.99 for c in closes[:-1]] + [12.8])
        assert sr.detect_exhaustion("X", d) is None

    def test_needs_a_real_run(self):
        closes = [10.0] * 34 + [10.2]
        d = daily(closes, volumes=[1_000_000] * 34 + [4_000_000],
                  highs=[10.1] * 34 + [10.8], lows=[9.9] * 34 + [10.1])
        assert sr.detect_exhaustion("X", d) is None

    def test_bad_input(self):
        assert sr.detect_exhaustion("X", None) is None
        assert sr.detect_exhaustion("X", daily([10.0] * 10)) is None
        flat = daily([10.0] * 30, highs=[10.0] * 30, lows=[10.0] * 30)
        assert sr.detect_exhaustion("X", flat) is None       # zero range day

    def test_riot_like_run_is_stretched_but_not_exhausted(self):
        closes = [13.0] * 29 + [11.84, 14.02, 15.37, 14.76, 16.71, 17.66]
        d = daily(closes, volumes=[18_000_000] * 30 + [40_800_000, 83_800_000, 49_200_000,
                                                      45_100_000, 28_900_000])
        assert sr.detect_exhaustion("RIOT", d) is None
        s = sr.stretched("RIOT", d)
        assert s == {"symbol": "RIOT", "price": 17.66, "move_5d_pct": 49.2, "direction": "up"}

    def test_stretched_down_and_not_stretched(self):
        assert sr.stretched("X", daily([20.0] * 25 + [19, 18, 16, 14, 13.0]))["direction"] == "down"
        assert sr.stretched("X", daily([20.0] * 30)) is None
        assert sr.stretched("X", None) is None


# -------------------------------------------------------------------- sympathy

class TestSympathy:
    GROUPS = {"miners": ["RIOT", "MARA", "CLSK", "HUT"], "chips": ["NVDA", "AMD"]}

    def test_leader_and_laggards(self):
        changes = {"RIOT": (12.0, 3.0), "MARA": (1.0, 1.0), "CLSK": (-0.5, 0.9),
                   "HUT": (9.0, 2.0), "NVDA": (0.5, 1.0), "AMD": (0.2, 1.0)}
        out = sr.find_sympathy(changes, self.GROUPS)
        assert len(out) == 1 and out[0]["group"] == "miners" and out[0]["leader"] == "RIOT"
        assert [x["symbol"] for x in out[0]["laggards"]] == ["CLSK", "MARA"]   # HUT already moved

    def test_big_move_on_no_volume_is_not_a_leader(self):
        assert sr.find_sympathy({"RIOT": (12.0, 0.8), "MARA": (0.0, 1.0)}, self.GROUPS) == []

    def test_no_laggards_means_no_row(self):
        changes = {"RIOT": (12.0, 3.0), "MARA": (9.0, 2.0), "CLSK": (-6.0, 2.0)}
        assert sr.find_sympathy(changes, self.GROUPS) == []

    def test_missing_members_and_empty_input(self):
        assert sr.find_sympathy({}, self.GROUPS) == []
        out = sr.find_sympathy({"RIOT": (12.0, 3.0), "MARA": (0.1, 1.0)}, self.GROUPS)
        assert out[0]["laggards"] == [{"symbol": "MARA", "change_pct": 0.1}]

    def test_day_change(self):
        d = daily([10.0] * 25 + [11.0], volumes=[1_000_000] * 25 + [3_000_000])
        pct, rvol = sr.day_change(d)
        assert pct == pytest.approx(10.0) and rvol == pytest.approx(3.0)
        assert sr.day_change(daily([10.0] * 5)) is None and sr.day_change(None) is None

    def test_peer_groups_include_the_extra_groups(self):
        groups = sr.peer_groups()
        assert "RIOT" in groups["crypto_miners"] and "semiconductors" in groups
        uni = sr.default_universe()
        assert "RIOT" in uni and "IREN" in uni and all(s.isalpha() for s in uni)
        assert "BRK-B" not in uni          # one malformed symbol fails the whole batch
        assert len(uni) == len(set(uni))


# ------------------------------------------------------------------------ scan

@pytest.fixture
def feeds(monkeypatch):
    f = {"daily": {}, "intraday": {}, "fail": set(), "open": True}
    sr._cache.clear()
    monkeypatch.setattr(sr, "_profile", {})
    monkeypatch.setattr(sr, "_profile_date", "")

    def multi(symbols, days=200, timeframe=None):
        if "daily" in f["fail"]:
            raise RuntimeError("alpaca down")
        return {s: f["daily"][s] for s in symbols if s in f["daily"]}

    def intraday(symbols, minutes_back=400, timeframe_minutes=5):
        if "intraday" in f["fail"]:
            raise RuntimeError("alpaca down")
        return {s: f["intraday"][s] for s in symbols if s in f["intraday"]}

    import src.scanner.intraday_movers as im
    monkeypatch.setattr(sr.client, "get_multi_bars", multi)
    monkeypatch.setattr(sr.client, "get_intraday_multi_bars", intraday)
    monkeypatch.setattr(im, "is_market_hours", lambda now=None: f["open"])
    monkeypatch.setattr("src.data.news.latest_headlines",
                        lambda symbols, **k: {s: [{"headline": f"{s} news"}] for s in symbols})
    return f


class TestScan:
    def test_intraday_and_daily_events_together(self, feeds, monkeypatch):
        # yesterday's range 99-101; today breaks out on volume then fails
        closes = [100.0] * 34 + [100.0]
        feeds["daily"]["FAIL"] = daily(closes, highs=[101.0] * 35, lows=[99.0] * 35)
        feeds["intraday"]["FAIL"] = session(
            [FLAT_BAR, (100.0, 101.6, 100.0, 101.5, 1), (101.5, 101.6, 100.4, 100.5, 1), FLAT_BAR[:3] + (100.5, 1)])
        r = sr.scan_spikes_reversals(["FAIL"], now=NOW)
        assert [(e["symbol"], e["kind"]) for e in r["events"]] == [("FAIL", "failed_breakout")]
        assert r["events"][0]["headline"] == "FAIL news"
        assert r["market_open"] is True and r["data_ok"] is True

    def test_closed_market_skips_intraday_and_says_so(self, feeds):
        feeds["open"] = False
        feeds["daily"]["X"] = daily([100.0] * 35)
        r = sr.scan_spikes_reversals(["X"], now=NOW)
        assert r["events"] == [] and r["market_open"] is False
        assert any("Market is closed" in n for n in r["notes"])

    def test_ignition_needs_the_profile_and_reports_when_it_is_missing(self, feeds, monkeypatch):
        feeds["daily"]["X"] = daily([100.0] * 35, highs=[101.0] * 35, lows=[99.0] * 35)
        feeds["intraday"]["X"] = session(
            [FLAT_BAR, FLAT_BAR, FLAT_BAR, (100.0, 102.5, 100.0, 102.4, 90_000)])
        r = sr.scan_spikes_reversals(["X"], now=NOW)
        assert r["events"] == [] and any("still loading" in n for n in r["notes"])
        monkeypatch.setattr(sr, "_profile", {"X": {"09:45": 10_000.0}})
        monkeypatch.setattr(sr, "_profile_date", NOW.date().isoformat())
        r = sr.scan_spikes_reversals(["X"], now=NOW)
        assert [(e["kind"], e["direction"]) for e in r["events"]] == [("volume_ignition", "up")]

    def test_price_data_failure(self, feeds):
        feeds["fail"].add("daily")
        r = sr.scan_spikes_reversals(["X"], now=NOW)
        assert r["data_ok"] is False and r["events"] == []

    def test_intraday_failure_keeps_daily_signals(self, feeds):
        feeds["fail"].add("intraday")
        closes = [13.0] * 29 + [11.84, 14.02, 15.37, 14.76, 16.71, 17.66]
        feeds["daily"]["RIOT"] = daily(closes)
        r = sr.scan_spikes_reversals(["RIOT"], now=NOW)
        assert r["stretched"][0]["symbol"] == "RIOT" and r["stretched"][0]["headline"] == "RIOT news"
        assert any("Intraday data unavailable" in n for n in r["notes"])

    def test_crypto_and_short_history_are_skipped(self, feeds):
        feeds["daily"]["NEW"] = daily([10.0] * 5)
        r = sr.scan_spikes_reversals(["BTC/USD", "NEW"], now=NOW)
        assert r["events"] == [] and r["stretched"] == []

    def test_one_bad_symbol_does_not_stop_the_rest(self, feeds):
        bad = daily([100.0] * 35)
        bad["close"] = "not a number"
        feeds["daily"]["BAD"] = bad
        closes = [13.0] * 29 + [11.84, 14.02, 15.37, 14.76, 16.71, 17.66]
        feeds["daily"]["RIOT"] = daily(closes)
        r = sr.scan_spikes_reversals(["BAD", "RIOT"], now=NOW)
        assert [s["symbol"] for s in r["stretched"]] == ["RIOT"]
