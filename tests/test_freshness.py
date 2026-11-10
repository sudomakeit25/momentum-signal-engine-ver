"""Data freshness measurement and alert labelling. No network."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.data import freshness as fr
from src.notifications import dispatcher as d

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 10, 10, 30, 20, tzinfo=ET)        # Tuesday, mid-session


def minute_bars(last_start: datetime, n=5):
    idx = pd.DatetimeIndex([last_start - timedelta(minutes=i) for i in range(n)][::-1])
    return pd.DataFrame({"close": 1.0, "volume": 1}, index=idx.tz_convert("UTC"))


@pytest.fixture
def feed(monkeypatch):
    state = {"bars": {}, "error": None, "calls": 0}
    monkeypatch.setattr(fr, "_cache", None)
    def fake(symbols, minutes_back=90, timeframe_minutes=1):
        state["calls"] += 1
        assert timeframe_minutes == 1
        if state["error"]:
            raise state["error"]
        return state["bars"]
    monkeypatch.setattr(fr.client, "get_intraday_multi_bars", fake)
    return state


class TestMeasure:
    def test_fifteen_minutes_behind(self):
        bars = {"SPY": minute_bars(NOW.replace(second=0) - timedelta(minutes=16))}
        assert fr.measure_delay(bars, NOW) == 15

    def test_current_data(self):
        bars = {"SPY": minute_bars(NOW.replace(second=0) - timedelta(minutes=1))}
        assert fr.measure_delay(bars, NOW) == 0

    def test_uses_the_freshest_symbol(self):
        bars = {"OLD": minute_bars(NOW.replace(second=0) - timedelta(minutes=40)),
                "NEW": minute_bars(NOW.replace(second=0) - timedelta(minutes=16))}
        assert fr.measure_delay(bars, NOW) == 15

    def test_empty_and_naive_and_reversed(self):
        assert fr.measure_delay({}, NOW) is None
        assert fr.measure_delay({"SPY": pd.DataFrame(), "QQQ": None}, NOW) is None
        b = minute_bars(NOW.replace(second=0) - timedelta(minutes=16)).iloc[::-1]
        b.index = b.index.tz_localize(None)
        assert fr.measure_delay({"SPY": b}, NOW) == 15

    def test_bar_from_the_future_is_not_negative(self):
        bars = {"SPY": minute_bars(NOW.replace(second=0) + timedelta(minutes=3))}
        assert fr.measure_delay(bars, NOW) == 0


class TestDataDelay:
    def test_delayed_plan(self, feed):
        feed["bars"] = {"SPY": minute_bars(NOW.replace(second=0) - timedelta(minutes=16))}
        out = fr.data_delay(NOW)
        assert out["session_active"] and out["delayed"] and out["delay_minutes"] == 15
        assert "15 minutes behind" in out["note"]
        assert fr.label(NOW) == " (15m delayed)"

    def test_real_time_plan_shows_no_label(self, feed):
        feed["bars"] = {"SPY": minute_bars(NOW.replace(second=0) - timedelta(minutes=1))}
        out = fr.data_delay(NOW)
        assert out["delayed"] is False and out["note"] == "" and fr.label(NOW) == ""

    def test_just_under_the_threshold(self, feed):
        feed["bars"] = {"SPY": minute_bars(NOW.replace(second=0) - timedelta(minutes=5))}
        assert fr.data_delay(NOW)["delayed"] is False            # 4 minutes behind

    def test_closed_sessions_make_no_request(self, feed):
        for when in (datetime(2026, 11, 14, 11, 0, tzinfo=ET),           # Saturday
                     datetime(2026, 11, 10, 3, 0, tzinfo=ET),            # before 4 AM
                     datetime(2026, 11, 10, 21, 0, tzinfo=ET)):          # after 8 PM
            out = fr.data_delay(when)
            assert out["session_active"] is False and out["delay_minutes"] is None
        assert feed["calls"] == 0

    def test_premarket_is_measured(self, feed):
        pre = datetime(2026, 11, 10, 6, 9, 0, tzinfo=ET)
        feed["bars"] = {"SPY": minute_bars(pre - timedelta(minutes=16))}
        assert fr.data_delay(pre)["delay_minutes"] == 15

    def test_feed_failure_and_no_bars_claim_nothing(self, feed):
        feed["error"] = RuntimeError("alpaca down")
        out = fr.data_delay(NOW)
        assert out["delay_minutes"] is None and out["delayed"] is False and fr.label(NOW) == ""
        feed["error"] = None
        assert fr.data_delay(NOW)["delay_minutes"] is None

    def test_a_long_gap_is_not_reported_as_the_plan_delay(self, feed):
        feed["bars"] = {"SPY": minute_bars(NOW.replace(second=0) - timedelta(hours=3))}
        out = fr.data_delay(NOW)                                  # holiday / halt / outage
        assert out["delay_minutes"] is None and out["delayed"] is False

    def test_cached_for_a_minute(self, feed, monkeypatch):
        clock = {"t": 1_000.0}
        monkeypatch.setattr(fr.time, "time", lambda: clock["t"])
        fr.data_delay(); fr.data_delay()
        first = feed["calls"]
        clock["t"] += 61
        fr.data_delay()
        assert first <= 1 and feed["calls"] <= first + 1

    def test_route(self, feed):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        app = FastAPI(); app.include_router(router)
        body = TestClient(app).get("/data/freshness").json()
        assert set(body) >= {"session_active", "delay_minutes", "delayed", "note"}


class TestAlertLabel:
    def _signal(self):
        from src.data.models import SetupType, Signal, SignalAction
        return Signal(symbol="NVDA", action=SignalAction.BUY, setup_type=SetupType.HIGHER_LOW,
                      entry=100.0, stop_loss=99.0, target=102.0, rr_ratio=2.0, confidence=0.65,
                      timestamp=NOW)

    def _watch(self):
        from src.data.models import IntradayWatch
        return IntradayWatch(symbol="SNDK", watch_type="box_forming", detail="d",
                             upper=890.0, lower=884.0, timestamp=NOW)

    def _pattern(self):
        from types import SimpleNamespace as NS
        return NS(symbol="AMD", pattern_type="v_reversal", trigger_price=500.0,
                  move_pct=-3.0, recovery_pct=2.5)

    def test_all_three_alert_kinds_carry_the_label(self):
        with d.alert_label(" (15m delayed)"):
            assert d._format_sms_body([self._signal()]).splitlines()[0] == "MSE Alert (15m delayed)"
            assert d._format_watch_body([self._watch()]).splitlines()[0] == "MSE Watch (15m delayed)"
            assert d._format_intraday_body([self._pattern()]).splitlines()[0] == \
                "MSE Intraday (15m delayed)"

    def test_no_label_outside_the_block_or_when_empty(self):
        with d.alert_label(" (15m delayed)"):
            pass
        assert d._format_sms_body([self._signal()]).splitlines()[0] == "MSE Alert"
        with d.alert_label(""):
            assert d._format_watch_body([self._watch()]).splitlines()[0] == "MSE Watch"
        with d.alert_label(None):
            assert d._format_sms_body([self._signal()]).splitlines()[0] == "MSE Alert"

    def test_label_is_cleared_even_if_the_dispatch_raises(self):
        with pytest.raises(RuntimeError):
            with d.alert_label(" (15m delayed)"):
                raise RuntimeError("smtp down")
        assert d._format_sms_body([self._signal()]).splitlines()[0] == "MSE Alert"

    def test_labelled_body_still_fits_one_sms(self):
        from src.data.models import SetupType, Signal, SignalAction
        many = [Signal(symbol=f"SYM{i}", action=SignalAction.BUY, setup_type=SetupType.HIGHER_LOW,
                       entry=100.0 + i, stop_loss=99.0, target=102.0, rr_ratio=2.0,
                       confidence=0.65, timestamp=NOW) for i in range(20)]
        with d.alert_label(" (15m delayed)"):
            assert len(d._format_sms_body(many)) <= 155
            assert len(d._format_watch_body([self._watch()] * 12)) <= 155

    def test_label_does_not_leak_across_threads(self):
        import threading
        seen = {}
        def other():
            seen["header"] = d._format_sms_body([self._signal()]).splitlines()[0]
        with d.alert_label(" (15m delayed)"):
            t = threading.Thread(target=other); t.start(); t.join()
        assert seen["header"] == "MSE Alert"
