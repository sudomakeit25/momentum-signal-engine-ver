"""Keep-alive loop: when it requests the service's own address, and that no
bad setting, missing address or failed request can break it."""

import threading
from datetime import datetime, time as dtime, timezone

import pytest
import requests

from src import keepalive as ka


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setattr(ka.settings, "keep_alive_enabled", True)
    monkeypatch.setattr(ka.settings, "keep_alive_url", "")
    monkeypatch.setattr(ka.settings, "keep_alive_start_et", "04:00")
    monkeypatch.setattr(ka.settings, "keep_alive_end_et", "16:15")
    monkeypatch.setattr(ka.settings, "keep_alive_interval_seconds", 300)
    monkeypatch.setattr(ka, "STARTUP_DELAY", 0)
    monkeypatch.setattr(ka, "_state", {"pings": 0, "failures": 0, "last_ok_at": None,
                                       "last_attempt_at": None, "last_error": None})


class _Resp:
    def __init__(self, code=200):
        self.status_code = code


class TestWindow:
    # 2026-11-10 is a Tuesday in winter time (New York = UTC-5).
    def test_winter_start_boundary(self):
        assert ka.in_window(_utc(2026, 11, 10, 8, 59)) is False   # 03:59
        assert ka.in_window(_utc(2026, 11, 10, 9, 0)) is True     # 04:00

    def test_winter_end_boundary(self):
        assert ka.in_window(_utc(2026, 11, 10, 21, 15)) is True   # 16:15
        assert ka.in_window(_utc(2026, 11, 10, 21, 16)) is False  # 16:16

    def test_end_minute_is_inclusive_to_the_last_second(self):
        late = datetime(2026, 11, 10, 21, 15, 59, 999000, tzinfo=timezone.utc)
        assert ka.in_window(late) is True

    # 2026-07-14 is a Tuesday in summer time (New York = UTC-4).
    def test_summer_boundaries(self):
        assert ka.in_window(_utc(2026, 7, 14, 7, 59)) is False    # 03:59
        assert ka.in_window(_utc(2026, 7, 14, 8, 0)) is True      # 04:00
        assert ka.in_window(_utc(2026, 7, 14, 20, 15)) is True    # 16:15
        assert ka.in_window(_utc(2026, 7, 14, 20, 16)) is False   # 16:16

    def test_covers_the_whole_regular_session(self):
        for hour in range(15, 21):                                # 10:00 to 15:00
            assert ka.in_window(_utc(2026, 11, 10, hour)) is True

    def test_weekend_is_closed(self):
        assert ka.in_window(_utc(2026, 11, 14, 15)) is False      # Saturday 10:00
        assert ka.in_window(_utc(2026, 11, 15, 15)) is False      # Sunday 10:00

    def test_weekday_is_judged_in_new_york_not_utc(self):
        # Saturday 01:00 UTC is still Friday 20:00 in New York: after the window.
        assert ka.in_window(_utc(2026, 11, 14, 1)) is False
        # Monday 09:30 UTC is Monday 04:30 in New York: inside.
        assert ka.in_window(_utc(2026, 11, 16, 9, 30)) is True
        # Friday 21:00 UTC is Friday 16:00: inside, the last weekday.
        assert ka.in_window(_utc(2026, 11, 13, 21)) is True

    def test_naive_time_is_read_as_utc(self):
        assert ka.in_window(datetime(2026, 11, 10, 15, 0)) is True
        assert ka.in_window(datetime(2026, 11, 10, 3, 0)) is False

    def test_custom_window(self, monkeypatch):
        monkeypatch.setattr(ka.settings, "keep_alive_start_et", "09:00")
        monkeypatch.setattr(ka.settings, "keep_alive_end_et", "10:00")
        assert ka.in_window(_utc(2026, 11, 10, 13, 59)) is False
        assert ka.in_window(_utc(2026, 11, 10, 14, 30)) is True
        assert ka.in_window(_utc(2026, 11, 10, 15, 1)) is False

    @pytest.mark.parametrize("bad", ["", "abc", "25:00", "9", "09:61", "09:00:00", None])
    def test_malformed_times_fall_back_to_defaults(self, monkeypatch, bad):
        monkeypatch.setattr(ka.settings, "keep_alive_start_et", bad)
        monkeypatch.setattr(ka.settings, "keep_alive_end_et", bad)
        assert ka.window() == (ka.DEFAULT_START, ka.DEFAULT_END)

    def test_reversed_window_falls_back_to_defaults(self, monkeypatch):
        monkeypatch.setattr(ka.settings, "keep_alive_start_et", "16:15")
        monkeypatch.setattr(ka.settings, "keep_alive_end_et", "04:00")
        assert ka.window() == (dtime(4, 0), dtime(16, 15))
        assert ka.in_window(_utc(2026, 11, 10, 15)) is True

    def test_zero_length_window_falls_back_to_defaults(self, monkeypatch):
        monkeypatch.setattr(ka.settings, "keep_alive_start_et", "10:00")
        monkeypatch.setattr(ka.settings, "keep_alive_end_et", "10:00")
        assert ka.window() == (ka.DEFAULT_START, ka.DEFAULT_END)


class TestInterval:
    @pytest.mark.parametrize("given,expected", [
        (300, 300), (0, 60), (-5, 60), (10, 60), (3600, 780), ("abc", 300), (None, 300),
    ])
    def test_clamped_below_the_sleep_threshold(self, monkeypatch, given, expected):
        monkeypatch.setattr(ka.settings, "keep_alive_interval_seconds", given)
        assert ka.interval() == expected
        assert ka.interval() < 15 * 60


class TestTargetUrl:
    def test_none_when_nothing_is_set(self):
        assert ka.target_url() == ""

    def test_uses_render_address(self, monkeypatch):
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        assert ka.target_url() == "https://example.onrender.com/health"

    def test_setting_wins_over_render_address(self, monkeypatch):
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        monkeypatch.setattr(ka.settings, "keep_alive_url", "https://mine.example.com/")
        assert ka.target_url() == "https://mine.example.com/health"

    def test_path_and_query_are_dropped(self, monkeypatch):
        monkeypatch.setattr(ka.settings, "keep_alive_url", "https://mine.example.com/a/b?x=1")
        assert ka.target_url() == "https://mine.example.com/health"

    @pytest.mark.parametrize("bad", ["example.com", "ftp://example.com", "https://", "   ", "file:///etc/passwd"])
    def test_rejects_anything_that_is_not_http(self, monkeypatch, bad):
        monkeypatch.setattr(ka.settings, "keep_alive_url", bad)
        assert ka.target_url() == ""


class TestPing:
    def test_success_is_recorded(self, monkeypatch):
        seen = {}

        def fake_get(url, timeout=None, headers=None):
            seen.update(url=url, timeout=timeout)
            return _Resp(200)

        monkeypatch.setattr(ka.requests, "get", fake_get)
        assert ka.ping("https://x.example/health") is True
        assert seen["url"] == "https://x.example/health"
        assert seen["timeout"]                      # never an unbounded wait
        assert ka._state["pings"] == 1 and ka._state["failures"] == 0
        assert ka._state["last_error"] is None and ka._state["last_ok_at"]

    @pytest.mark.parametrize("code", [400, 404, 500, 502, 503])
    def test_error_status_is_a_failure(self, monkeypatch, code):
        monkeypatch.setattr(ka.requests, "get", lambda *a, **k: _Resp(code))
        assert ka.ping("https://x.example/health") is False
        assert ka._state["last_error"] == f"HTTP {code}"
        assert ka._state["failures"] == 1 and ka._state["last_ok_at"] is None

    @pytest.mark.parametrize("exc", [
        requests.ConnectionError("refused"), requests.Timeout("slow"),
        requests.exceptions.InvalidURL("bad"), RuntimeError("anything"),
    ])
    def test_never_raises(self, monkeypatch, exc):
        def boom(*a, **k):
            raise exc

        monkeypatch.setattr(ka.requests, "get", boom)
        assert ka.ping("https://x.example/health") is False
        assert type(exc).__name__ in ka._state["last_error"]

    def test_recovery_clears_the_error(self, monkeypatch):
        monkeypatch.setattr(ka.requests, "get", lambda *a, **k: _Resp(503))
        ka.ping("https://x.example/health")
        monkeypatch.setattr(ka.requests, "get", lambda *a, **k: _Resp(200))
        assert ka.ping("https://x.example/health") is True
        assert ka._state["last_error"] is None
        assert ka._state["pings"] == 1 and ka._state["failures"] == 1


class _Stop:
    """Stands in for threading.Event: records each wait and stops the loop
    after a set number of cycles, so the loop runs without real sleeping."""

    def __init__(self, cycles):
        self.cycles, self.waits = cycles, []

    def is_set(self):
        return len(self.waits) >= self.cycles

    def wait(self, seconds):
        self.waits.append(seconds)


class TestRun:
    def _count(self, monkeypatch, result=True):
        calls = []

        def fake_ping(url):
            calls.append(url)
            return result() if callable(result) else result

        monkeypatch.setattr(ka, "ping", fake_ping)
        return calls

    def test_does_nothing_without_an_address(self, monkeypatch):
        calls = self._count(monkeypatch)
        stop = _Stop(3)
        ka.run(stop)
        assert calls == [] and stop.waits == []     # returned at once

    def test_does_nothing_when_switched_off(self, monkeypatch):
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        monkeypatch.setattr(ka.settings, "keep_alive_enabled", False)
        calls = self._count(monkeypatch)
        stop = _Stop(3)
        ka.run(stop)
        assert calls == [] and stop.waits == []

    def test_requests_every_cycle_inside_the_window(self, monkeypatch):
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        monkeypatch.setattr(ka, "in_window", lambda now=None: True)
        calls = self._count(monkeypatch)
        stop = _Stop(3)
        ka.run(stop)
        assert calls == ["https://example.onrender.com/health"] * 3
        assert stop.waits == [300, 300, 300]

    def test_silent_outside_the_window(self, monkeypatch):
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        monkeypatch.setattr(ka, "in_window", lambda now=None: False)
        calls = self._count(monkeypatch)
        stop = _Stop(3)
        ka.run(stop)
        assert calls == [] and stop.waits == [300, 300, 300]

    def test_failed_request_is_retried_sooner(self, monkeypatch):
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        monkeypatch.setattr(ka, "in_window", lambda now=None: True)
        answers = iter([False, True, True])
        calls = self._count(monkeypatch, result=lambda: next(answers))
        stop = _Stop(3)
        ka.run(stop)
        assert len(calls) == 3
        assert stop.waits == [60, 300, 300]

    def test_a_crashing_cycle_does_not_end_the_loop(self, monkeypatch):
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        monkeypatch.setattr(ka, "in_window", lambda now=None: True)

        def boom(url):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(ka, "ping", boom)
        stop = _Stop(4)
        ka.run(stop)                                 # must not raise
        assert len(stop.waits) == 4

    def test_waits_for_the_server_before_the_first_request(self, monkeypatch):
        # Found live: the loop starts before the server listens, so an
        # immediate request failed and logged a warning on every start.
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        monkeypatch.setattr(ka, "in_window", lambda now=None: True)
        monkeypatch.setattr(ka, "STARTUP_DELAY", 45)
        order = []
        monkeypatch.setattr(ka, "ping", lambda url: order.append("ping") or True)

        class Stop(_Stop):
            def wait(self, seconds):
                order.append(seconds)
                super().wait(seconds)

        ka.run(Stop(2))
        assert order == [45, "ping", 300]

    def test_stops_when_the_event_is_set(self, monkeypatch):
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        calls = self._count(monkeypatch)
        stop = threading.Event()
        stop.set()
        ka.run(stop)
        assert calls == []


class TestStatus:
    def test_reports_off_without_an_address(self):
        s = ka.status()
        assert s["enabled"] is True and s["active"] is False and s["url"] is None
        assert s["window_et"] == "04:00 to 16:15 weekdays"

    def test_reports_last_result(self, monkeypatch):
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
        monkeypatch.setattr(ka.requests, "get", lambda *a, **k: _Resp(200))
        ka.ping(ka.target_url())
        s = ka.status()
        assert s["active"] is True and s["pings"] == 1 and s["last_error"] is None
        assert s["last_ok_at"].startswith("20") and s["interval_seconds"] == 300

    def test_route_answers(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from src.api.routes import router

        app = FastAPI()
        app.include_router(router)
        r = TestClient(app).get("/health/keepalive")
        assert r.status_code == 200
        assert {"enabled", "active", "window_et", "in_window_now", "pings"} <= set(r.json())


class TestWiring:
    def test_settings_declare_every_key(self):
        from config.settings import Settings
        fields = Settings.model_fields
        for key in ("keep_alive_enabled", "keep_alive_url", "keep_alive_start_et",
                    "keep_alive_end_et", "keep_alive_interval_seconds"):
            assert key in fields
        assert fields["keep_alive_enabled"].default is True

    def test_started_with_the_other_loops(self):
        import inspect
        from src import main
        assert "keepalive.run" in inspect.getsource(main.lifespan)
