"""Rules every alert passes: only while the market is open, and no alert that
contradicts one on the same stock from the last hour, across all scanners.

Cases from the real sessions: daily signals arrived at 16:04 on 2026-11-11
and 16:12 on 2026-11-12; on 2026-11-12 AMD got pattern SELLs at 10:33 and
12:43, a movers BUY at 13:11 and a daily-signal BUY at 15:46."""

import inspect
import threading
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest

from src.notifications import alert_rules as ar

ET = ZoneInfo("America/New_York")


def ts(h, m=0, day=12):
    return datetime(2026, 11, day, h, m, tzinfo=ET).timestamp()


def pattern(sym, kind):
    return NS(symbol=sym, pattern_type=kind)


def signal(sym, action):
    return NS(symbol=sym, action=NS(value=action))


def watch(sym):
    return NS(symbol=sym, watch_type="box_forming")


class _Redis:
    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    redis = _Redis()
    monkeypatch.setattr(ar, "_redis", lambda: redis)
    monkeypatch.setattr(ar, "_recent", {})
    monkeypatch.setattr(ar, "_loaded", False)
    monkeypatch.setattr(ar, "_trading_days", {})
    from src.notifications import heartbeat
    monkeypatch.setattr(heartbeat, "_trading_day", lambda day: True)
    return redis


def restart(monkeypatch):
    """What a server restart loses: the in-memory record."""
    monkeypatch.setattr(ar, "_recent", {})
    monkeypatch.setattr(ar, "_loaded", False)


class TestMarketHours:
    @pytest.mark.parametrize("h,m,expected", [
        (9, 29, False), (9, 30, True), (12, 0, True), (15, 59, True), (16, 0, False),
        (16, 12, False), (4, 0, False), (20, 0, False)])
    def test_open_from_9_30_to_4_pm_new_york(self, h, m, expected):
        assert ar.market_open(datetime(2026, 11, 12, h, m, tzinfo=ET)) is expected

    @pytest.mark.parametrize("day", [14, 15])          # Saturday, Sunday
    def test_closed_on_weekends(self, day):
        assert ar.market_open(datetime(2026, 11, day, 11, 0, tzinfo=ET)) is False

    def test_closed_on_market_holidays_and_the_calendar_is_asked_once_a_day(self, monkeypatch):
        from src.notifications import heartbeat
        asked = []
        monkeypatch.setattr(heartbeat, "_trading_day", lambda day: asked.append(day) or False)
        assert ar.market_open(datetime(2026, 11, 26, 11, 0, tzinfo=ET)) is False   # Thanksgiving
        assert ar.market_open(datetime(2026, 11, 26, 14, 0, tzinfo=ET)) is False
        assert len(asked) == 1

    def test_a_naive_time_is_read_as_utc(self):
        assert ar.market_open(datetime(2026, 11, 12, 15, 0)) is True        # 10:00 New York
        assert ar.market_open(datetime(2026, 11, 12, 21, 12)) is False      # 16:12 New York


class TestDirection:
    @pytest.mark.parametrize("item,want", [
        (pattern("A", "v_reversal"), "up"), (pattern("A", "breakout"), "up"),
        (pattern("A", "inverted_v"), "down"), (pattern("A", "breakdown"), "down"),
        (signal("A", "BUY"), "up"), (signal("A", "SELL"), "down"),
        (NS(symbol="A", action="buy"), "up"), (watch("A"), None), (NS(symbol="A"), None)])
    def test_directions(self, item, want):
        assert ar.direction_of(item) == want


class TestClaim:
    def test_opposite_alert_within_the_hour_is_held(self):
        assert ar.claim([pattern("QCOM", "breakout")], ts(10, 12))[0]
        send, held = ar.claim([pattern("QCOM", "inverted_v")], ts(10, 20))
        assert send == [] and len(held) == 1

    def test_after_the_hour_it_goes_out(self):
        ar.claim([pattern("QCOM", "breakout")], ts(10, 12))
        send, held = ar.claim([pattern("QCOM", "breakdown")], ts(11, 13))
        assert len(send) == 1 and held == []

    def test_same_direction_and_other_stocks_go_out(self):
        ar.claim([pattern("AMD", "breakout")], ts(11, 0))
        send, held = ar.claim([signal("AMD", "BUY"), signal("NVDA", "SELL")], ts(11, 10))
        assert len(send) == 2 and held == []

    def test_across_scanners(self):
        ar.claim([pattern("AMD", "breakdown")], ts(12, 43))
        send, held = ar.claim([signal("AMD", "BUY")], ts(13, 11))      # a movers setup or daily signal
        assert send == [] and len(held) == 1

    def test_both_directions_in_one_batch_are_both_held(self):
        send, held = ar.claim([signal("X", "BUY"), signal("X", "SELL"), signal("Y", "BUY")], ts(10))
        assert [s.symbol for s in send] == ["Y"] and len(held) == 2

    def test_batch_order_does_not_matter(self):
        a = [signal("X", "BUY"), signal("X", "SELL")]
        assert len(ar.claim(a, ts(10))[1]) == 2
        assert len(ar.claim(a[::-1], ts(13))[1]) == 2

    def test_alerts_without_a_direction_always_go_out(self):
        ar.claim([signal("AMD", "SELL")], ts(10))
        send, held = ar.claim([watch("AMD")], ts(10, 5))
        assert len(send) == 1 and held == []

    def test_held_alerts_are_not_recorded(self):
        ar.claim([pattern("AMD", "inverted_v")], ts(10, 33))
        ar.claim([pattern("AMD", "breakout")], ts(11, 8))               # held
        send, _ = ar.claim([pattern("AMD", "breakdown")], ts(11, 40))   # still only "down" on record
        assert len(send) == 1

    def test_empty(self):
        assert ar.claim([], ts(10)) == ([], [])

    def test_the_record_survives_a_restart(self, monkeypatch, clean):
        ar.claim([signal("AMD", "SELL")], ts(10))
        assert ar.RECENT_KEY in clean.d
        restart(monkeypatch)
        assert ar.claim([signal("AMD", "BUY")], ts(10, 30))[0] == []

    @pytest.mark.parametrize("junk", ["not json", "[]", '{"AMD": [["sideways", 1]]}', '{"AMD": "x"}',
                                      '{"AMD": [[1, 2, 3]]}'])
    def test_unreadable_record_is_ignored(self, monkeypatch, clean, junk):
        clean.d[ar.RECENT_KEY] = junk
        restart(monkeypatch)
        send, held = ar.claim([signal("AMD", "BUY")], ts(10))
        assert len(send) == 1

    def test_without_redis_it_still_works_in_memory(self, monkeypatch):
        monkeypatch.setattr(ar, "_redis", lambda: None)
        ar.claim([signal("AMD", "SELL")], ts(10))
        assert ar.claim([signal("AMD", "BUY")], ts(10, 5))[0] == []

    def test_a_failure_sends_rather_than_silences(self, monkeypatch):
        def boom():
            raise RuntimeError("redis exploded")
        monkeypatch.setattr(ar, "_load", boom)
        items = [signal("AMD", "BUY")]
        assert ar.claim(items, ts(10)) == (items, [])

    def test_two_loops_cannot_both_send_opposite_alerts(self):
        out, gate = [], threading.Barrier(2)

        def go(item):
            gate.wait()
            out.append(ar.claim([item], ts(10)))

        threads = [threading.Thread(target=go, args=(i,))
                   for i in (signal("AMD", "BUY"), pattern("AMD", "breakdown"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sum(len(send) for send, _ in out) == 1

    def test_amd_on_2026_11_12(self):
        sent = []
        for when, item in [((10, 33), pattern("AMD", "inverted_v")),
                           ((11, 8), pattern("AMD", "breakout")),
                           ((11, 23), pattern("AMD", "v_reversal")),
                           ((12, 43), pattern("AMD", "breakdown")),
                           ((13, 11), signal("AMD", "BUY")),          # movers higher low
                           ((15, 46), signal("AMD", "BUY"))]:        # daily breakout
            send, _ = ar.claim([item], ts(*when))
            sent += [when for _ in send]
        assert sent == [(10, 33), (12, 43), (15, 46)]


class TestWiring:
    def _src(self, name):
        from src import main
        return inspect.getsource(getattr(main, name))

    def test_daily_signals_are_held_outside_market_hours_and_on_conflict(self):
        src = self._src("_refresh_loop")
        assert src.index("alert_rules.market_open()") < src.index("dispatch_alerts(to_send)")
        assert src.index("alert_rules.claim(to_send)") < src.index("dispatch_alerts(to_send)")
        assert "track_signals(new_signals)" in src                  # still recorded

    def test_intraday_patterns_and_setups_pass_the_conflict_rule(self):
        src = self._src("_intraday_scan_loop")
        assert src.index("alert_rules.claim(new_patterns)") < src.index("dispatch_intraday_patterns(new_patterns)")
        assert src.index("alert_rules.claim(new_setups)") < src.index("dispatch_alerts(to_alert)")

    def test_the_paper_trader_still_sees_every_setup(self):
        src = self._src("_intraday_scan_loop")
        assert "auto_trader.handle_new_setups(\n                            new_setups" in src
