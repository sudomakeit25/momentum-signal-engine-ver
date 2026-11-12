"""Telegram status messages: the morning check before the open and the
restart notice. On 2026-11-11 the server ran out of memory a dozen times and
was down for the last two hours of the session without anyone being told."""

import json
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.notifications import heartbeat as hb

ET = ZoneInfo("America/New_York")


def at(h, m=0, day=12):
    """2026-11-12 is a Thursday."""
    return datetime(2026, 11, day, h, m, tzinfo=ET)


class _Redis:
    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v


@pytest.fixture(autouse=True)
def wire(monkeypatch):
    redis = _Redis()
    sent = []
    monkeypatch.setattr(hb, "_redis", lambda: redis)
    monkeypatch.setattr(hb, "_telegram_ready", lambda: True)
    monkeypatch.setattr(hb, "_send", lambda text: sent.append(text) or True)
    monkeypatch.setattr(hb, "_trading_day", lambda day: True)
    monkeypatch.setattr(hb, "_state", {"last_alive_write": 0.0, "heartbeat_date": "",
                                       "next_try": 0.0, "restarts_today": 2})
    monkeypatch.setattr(hb, "_boot_checked", threading.Event())
    monkeypatch.setattr(hb.settings, "heartbeat_enabled", True)
    monkeypatch.setattr(hb.settings, "heartbeat_et", "09:25")
    monkeypatch.setattr(hb.settings, "restart_notice_enabled", True)
    monkeypatch.setattr(hb.settings, "keep_alive_start_et", "04:00")
    monkeypatch.setattr(hb.settings, "keep_alive_end_et", "16:15")
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    # Parts of the morning message, so no test reads the network.
    from src import heavy
    from src.data import freshness
    from src.notifications import dispatcher
    from src.trading import auto_trader
    monkeypatch.setattr(heavy, "rss_mb", lambda: 186.0)
    monkeypatch.setattr(heavy, "peak_mb", lambda: 257.0)
    monkeypatch.setattr(freshness, "data_delay", lambda now=None: {"session_active": False})
    monkeypatch.setattr(auto_trader, "status", lambda: {"mode": "running", "paper": True, "trades": []})
    monkeypatch.setattr(dispatcher, "load_config",
                        lambda: dispatcher.NotificationConfig(auto_alerts_enabled=True, min_confidence=0.55))
    return redis, sent


class TestMorningCheck:
    def test_sent_once_at_9_25_on_a_trading_day(self, wire):
        redis, sent = wire
        assert hb.heartbeat_tick(at(9, 24)) is None
        text = hb.heartbeat_tick(at(9, 25))
        assert text and len(sent) == 1
        assert hb.heartbeat_tick(at(9, 26)) is None and len(sent) == 1
        assert redis.d[hb.HEARTBEAT_KEY] == "2026-11-12"

    def test_a_restart_does_not_send_it_twice(self, wire, monkeypatch):
        redis, sent = wire
        hb.heartbeat_tick(at(9, 25))
        monkeypatch.setattr(hb, "_state", {"last_alive_write": 0.0, "heartbeat_date": "",
                                           "next_try": 0.0, "restarts_today": 3})
        assert hb.heartbeat_tick(at(9, 40)) is None and len(sent) == 1

    def test_message_says_what_matters(self, wire):
        text = hb.heartbeat_tick(at(9, 25))
        assert text.splitlines()[0].startswith("MSE morning check, Thu Nov 12 9:25am ET")
        assert "memory 186 of 512 MB (peak 257)" in text
        assert "Starts today: 2" in text
        assert "Auto-trader: running (paper), 0 trades so far" in text
        assert "Alerts: on, minimum confidence 55%" in text
        assert "late" not in text

    def test_delay_and_alerts_off_are_reported(self, wire, monkeypatch):
        from src.data import freshness
        from src.notifications import dispatcher
        monkeypatch.setattr(freshness, "data_delay",
                            lambda now=None: {"session_active": True, "delayed": True, "delay_minutes": 15})
        monkeypatch.setattr(dispatcher, "load_config",
                            lambda: dispatcher.NotificationConfig(auto_alerts_enabled=False))
        text = hb.heartbeat_tick(at(9, 30))
        assert "Prices: about 15 min behind" in text and "Alerts: OFF" in text

    def test_late_when_the_server_was_down_at_the_set_time(self, wire):
        text = hb.heartbeat_tick(at(10, 41))
        assert "(late: the server was not running earlier)" in text

    def test_one_broken_part_does_not_stop_the_message(self, wire, monkeypatch):
        from src.trading import auto_trader

        def boom():
            raise RuntimeError("broker down")

        monkeypatch.setattr(auto_trader, "status", boom)
        text = hb.heartbeat_tick(at(9, 25))
        assert "Auto-trader: unknown" in text and "memory 186" in text

    @pytest.mark.parametrize("when", [at(9, 25, day=14), at(9, 25, day=15)])   # Saturday, Sunday
    def test_not_on_weekends(self, wire, when):
        assert hb.heartbeat_tick(when) is None and wire[1] == []

    @pytest.mark.parametrize("when", [at(16, 0), at(19, 0), at(3, 0)])
    def test_not_after_the_close_or_before_the_set_time(self, wire, when):
        assert hb.heartbeat_tick(when) is None and wire[1] == []

    def test_market_holiday_is_skipped_and_not_asked_again(self, wire, monkeypatch):
        asked = []
        monkeypatch.setattr(hb, "_trading_day", lambda day: asked.append(day) or False)
        assert hb.heartbeat_tick(at(9, 25)) is None
        assert hb.heartbeat_tick(at(9, 30)) is None
        assert wire[1] == [] and len(asked) == 1

    def test_needs_telegram_and_the_switch(self, wire, monkeypatch):
        monkeypatch.setattr(hb, "_telegram_ready", lambda: False)
        assert hb.heartbeat_tick(at(9, 25)) is None
        monkeypatch.setattr(hb, "_telegram_ready", lambda: True)
        monkeypatch.setattr(hb.settings, "heartbeat_enabled", False)
        assert hb.heartbeat_tick(at(9, 25)) is None
        assert wire[1] == []
        monkeypatch.setattr(hb.settings, "heartbeat_enabled", True)
        assert hb.heartbeat_tick(at(9, 26))                 # not marked as sent while off

    def test_failed_send_is_retried_after_a_wait(self, wire, monkeypatch):
        attempts = []
        monkeypatch.setattr(hb, "_send", lambda text: attempts.append(text) and False)
        assert hb.heartbeat_tick(at(9, 25)) is None
        assert hb.heartbeat_tick(at(9, 26)) is None
        assert len(attempts) == 1                          # waiting before the next try
        monkeypatch.setattr(hb, "_state", {**hb._state, "next_try": time.time() - 1})
        monkeypatch.setattr(hb, "_send", lambda text: attempts.append(text) or True)
        assert hb.heartbeat_tick(at(9, 31)) and len(attempts) == 2

    @pytest.mark.parametrize("setting,before,on", [("09:00", (8, 59), (9, 0)), ("bad", (9, 24), (9, 25))])
    def test_time_setting_and_bad_values(self, wire, monkeypatch, setting, before, on):
        monkeypatch.setattr(hb.settings, "heartbeat_et", setting)
        assert hb.heartbeat_tick(at(*before)) is None
        assert hb.heartbeat_tick(at(*on))

    def test_never_raises(self, wire, monkeypatch):
        def boom(*a):
            raise RuntimeError("redis exploded")

        monkeypatch.setattr(hb, "_redis", boom)
        hb.heartbeat_tick(at(9, 25))                       # must not raise


class TestRestartNotice:
    def _boot(self, redis, **kw):
        redis.d[hb.BOOT_KEY] = json.dumps({"commit": "abc1234", "date": "2026-11-12",
                                           "restarts": 0, "last_notice": 0, **kw})

    def test_crash_while_running(self, wire, monkeypatch):
        redis, sent = wire
        monkeypatch.setenv("RENDER_GIT_COMMIT", "abc1234ffff")
        self._boot(redis)
        redis.d[hb.ALIVE_KEY] = str(int(at(10, 58).timestamp()))
        text = hb.restart_notice(at(11, 0))
        assert "restarted at 11:00am ET unexpectedly, probably out of memory" in text
        assert "1st start today" in text and sent == [text]
        assert json.loads(redis.d[hb.BOOT_KEY])["restarts"] == 1

    def test_deploy(self, wire, monkeypatch):
        redis, _ = wire
        monkeypatch.setenv("RENDER_GIT_COMMIT", "def5678aaaa")
        self._boot(redis)
        redis.d[hb.ALIVE_KEY] = str(int(at(10, 59).timestamp()))
        assert "after a deploy (commit def5678)" in hb.restart_notice(at(11, 0))
        assert json.loads(redis.d[hb.BOOT_KEY])["commit"] == "def5678"

    def test_wake_after_being_down(self, wire):
        redis, _ = wire
        redis.d[hb.ALIVE_KEY] = str(int(at(8, 24).timestamp()))
        text = hb.restart_notice(at(10, 18))
        assert "after being down since 8:24am ET" in text

    def test_outside_the_awake_hours_it_is_counted_but_not_sent(self, wire):
        redis, sent = wire
        assert hb.restart_notice(at(20, 0)) is None
        assert sent == [] and json.loads(redis.d[hb.BOOT_KEY])["restarts"] == 1

    def test_a_crash_loop_sends_one_notice_per_half_hour(self, wire):
        redis, sent = wire
        assert hb.restart_notice(at(11, 0))
        assert hb.restart_notice(at(11, 10)) is None
        text = hb.restart_notice(at(11, 31))
        assert len(sent) == 2 and "3rd start today" in text

    def test_count_starts_over_each_day(self, wire):
        redis, _ = wire
        self._boot(redis, date="2026-11-11", restarts=12)
        assert "1st start today" in hb.restart_notice(at(9, 0))

    @pytest.mark.parametrize("junk", ["not json", "[]", "7"])
    def test_unreadable_history_is_treated_as_none(self, wire, junk):
        redis, _ = wire
        redis.d[hb.BOOT_KEY] = junk
        assert "1st start today" in hb.restart_notice(at(11, 0))

    def test_without_redis_it_still_says_it_restarted(self, wire, monkeypatch):
        monkeypatch.setattr(hb, "_redis", lambda: None)
        assert hb.restart_notice(at(11, 0)).startswith("MSE server restarted at 11:00am ET. 1st")

    def test_needs_telegram_and_the_switch(self, wire, monkeypatch):
        monkeypatch.setattr(hb.settings, "restart_notice_enabled", False)
        assert hb.restart_notice(at(11, 0)) is None
        monkeypatch.setattr(hb.settings, "restart_notice_enabled", True)
        monkeypatch.setattr(hb, "_telegram_ready", lambda: False)
        assert hb.restart_notice(at(11, 40)) is None
        assert wire[1] == []

    def test_unblocks_alive_marks_even_if_it_fails(self, wire, monkeypatch):
        monkeypatch.setattr(hb, "_ordinal", lambda n: 1 / 0)
        assert hb.restart_notice(at(11, 0)) is None
        assert hb._boot_checked.is_set()

    @pytest.mark.parametrize("n,want", [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"),
                                        (12, "12th"), (13, "13th"), (21, "21st"), (22, "22nd"), (111, "111th")])
    def test_ordinals(self, n, want):
        assert hb._ordinal(n) == want


class TestAlive:
    def test_not_written_before_the_restart_check_read_the_old_value(self, wire):
        redis, _ = wire
        assert hb.mark_alive(1000.0) is False and hb.ALIVE_KEY not in redis.d
        hb._boot_checked.set()
        assert hb.mark_alive(1000.0) is True and redis.d[hb.ALIVE_KEY] == "1000"

    def test_written_at_most_every_two_minutes(self, wire):
        redis, _ = wire
        hb._boot_checked.set()
        assert hb.mark_alive(1000.0)
        assert hb.mark_alive(1000.0 + hb.ALIVE_EVERY - 1) is False
        assert hb.mark_alive(1000.0 + hb.ALIVE_EVERY)

    def test_stop_before_the_check_still_unblocks(self, wire):
        stop = threading.Event()
        stop.set()
        hb.run(stop)
        assert hb._boot_checked.is_set()


class TestWiring:
    def test_started_with_the_app(self):
        import inspect
        from src import main
        assert "heartbeat.run" in inspect.getsource(main.lifespan)

    def test_settings_are_declared(self):
        from config.settings import Settings
        f = Settings.model_fields
        assert f["heartbeat_enabled"].default is True
        assert f["heartbeat_et"].default == "09:25"
        assert f["restart_notice_enabled"].default is True
