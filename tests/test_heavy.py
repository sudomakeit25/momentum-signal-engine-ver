"""Memory guard for the background loops (src/heavy.py), the volume profile
built in small pieces and saved, and the intraday bar cache that no longer
grows all day. Found in production on 2026-11-11: Render killed the process
for using over 512 MB a dozen times, because the loops' heavy steps ran at
the same time and the volume profile alone took memory from 88 MB to 479 MB."""

import inspect
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src import heavy


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(heavy, "_state", {"steps": {}, "skipped": {}, "waited_out": 0, "allocator": {}})
    monkeypatch.setattr(heavy, "_lock", threading.RLock())


class TestOneAtATime:
    def test_run_returns_the_result_and_records_the_step(self):
        assert heavy.run("adder", lambda a, b=0: a + b, 2, b=3) == 5
        step = heavy.status()["steps"]["adder"]
        assert step["seconds"] >= 0 and "mb_after" in step

    def test_steps_from_different_threads_never_overlap(self):
        running, most = [0], [0]
        guard = threading.Lock()

        def step():
            with guard:
                running[0] += 1
                most[0] = max(most[0], running[0])
            time.sleep(0.02)
            with guard:
                running[0] -= 1

        threads = [threading.Thread(target=heavy.run, args=(f"s{i}", step)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert most[0] == 1

    def test_nested_step_in_the_same_thread_does_not_deadlock(self):
        assert heavy.run("outer", lambda: heavy.run("inner", lambda: "ok")) == "ok"

    def test_a_failing_step_frees_the_slot_and_raises(self):
        def boom():
            raise ValueError("bad data")

        with pytest.raises(ValueError):
            heavy.run("boom", boom)
        done = []
        t = threading.Thread(target=lambda: done.append(heavy.run("next", lambda: 1)))
        t.start()
        t.join(timeout=2)
        assert done == [1]

    def test_a_step_stuck_elsewhere_cannot_block_forever(self, monkeypatch):
        monkeypatch.setattr(heavy, "WAIT_LIMIT", 0.1)
        hold, release = threading.Event(), threading.Event()

        def stuck():
            hold.set()
            release.wait(2)

        t = threading.Thread(target=heavy.run, args=("stuck", stuck))
        t.start()
        hold.wait(1)
        started = time.time()
        assert heavy.run("alerts", lambda: "sent") == "sent"
        assert time.time() - started < 1
        assert heavy.status()["waited_out"] == 1
        release.set()
        t.join()


class TestSkipOptional:
    def test_skips_when_memory_stays_high(self, monkeypatch):
        monkeypatch.setattr(heavy, "rss_mb", lambda: 400.0)
        assert heavy.should_skip("spike watch") is True
        assert heavy.should_skip("spike watch") is True
        assert heavy.status()["skipped"] == {"spike watch": 2}

    def test_runs_when_freeing_memory_is_enough(self, monkeypatch):
        readings = iter([400.0, 200.0])
        monkeypatch.setattr(heavy, "rss_mb", lambda: next(readings, 200.0))
        assert heavy.should_skip("spike watch") is False
        assert heavy.status()["skipped"] == {}

    @pytest.mark.parametrize("mb", [None, 0.0, 359.9, 360.0])
    def test_runs_at_or_below_the_line_or_when_unknown(self, monkeypatch, mb):
        monkeypatch.setattr(heavy, "rss_mb", lambda: mb)
        assert heavy.should_skip("x") is False

    def test_reading_never_raises(self):
        assert heavy.rss_mb() is None or heavy.rss_mb() > 0
        assert heavy.peak_mb() > 0
        heavy.release()


class TestAllocator:
    def test_no_op_off_linux(self, monkeypatch):
        monkeypatch.setattr(heavy.sys, "platform", "darwin")
        assert heavy.configure_allocator() == {}
        assert heavy.status()["allocator"] == {}

    def test_sets_arena_max_and_fixed_thresholds_on_linux(self, monkeypatch):
        calls = []

        class Libc:
            def mallopt(self, param, value):
                calls.append((param, value))
                return 1

        monkeypatch.setattr(heavy.sys, "platform", "linux")
        monkeypatch.setattr(heavy.ctypes, "CDLL", lambda name: Libc())
        applied = heavy.configure_allocator()
        assert applied == {"arena_max": True, "mmap_threshold": True, "trim_threshold": True}
        assert (-8, 2) in calls and (-3, 131072) in calls and (-1, 131072) in calls
        assert heavy.status()["allocator"] == applied

    def test_a_refused_setting_is_reported_and_a_missing_libc_never_raises(self, monkeypatch):
        class Libc:
            def mallopt(self, param, value):
                return 0 if param == -8 else 1

        monkeypatch.setattr(heavy.sys, "platform", "linux")
        monkeypatch.setattr(heavy.ctypes, "CDLL", lambda name: Libc())
        assert heavy.configure_allocator()["arena_max"] is False

        def missing(name):
            raise OSError("libc.so.6: cannot open shared object file")

        monkeypatch.setattr(heavy.ctypes, "CDLL", missing)
        assert heavy.configure_allocator() == {}

    def test_applied_when_the_app_module_loads(self):
        import inspect
        from src import main
        src = inspect.getsource(main)
        assert "heavy.configure_allocator()" in src
        assert src.index("heavy.configure_allocator()") < src.index("def lifespan")


class TestWiring:
    def _src(self, fn):
        from src import main
        return inspect.getsource(getattr(main, fn))

    def test_every_heavy_intraday_step_goes_through_the_guard(self):
        src = self._src("_intraday_scan_loop")
        for call in ('heavy.run("intraday patterns"', 'heavy.run("intraday movers"',
                     'heavy.run("volume profile"', 'heavy.run("spike watch"'):
            assert call in src, call
        assert src.index('heavy.should_skip("spike watch")') < src.index('heavy.run("volume profile"')

    def test_alert_and_trading_steps_are_never_skipped(self):
        src = self._src("_intraday_scan_loop")
        assert 'should_skip("intraday patterns")' not in src
        assert 'should_skip("intraday movers")' not in src

    def test_every_heavy_refresh_step_goes_through_the_guard(self):
        src = self._src("_refresh_loop")
        for name in ("daily scan", "cyclical scan", "short squeeze", "catalyst watch",
                     "pre-market gaps", "scorecard outcomes", "profile warmup"):
            assert f'"{name}"' in src, name
        assert 'with heavy.heavy("daily scan")' in src

    def test_startup_warmup_goes_through_the_guard(self):
        assert 'heavy.run("startup profile warmup"' in self._src("_warm_profile_cache_on_startup")

    def test_memory_route(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        app = FastAPI()
        app.include_router(router)
        r = TestClient(app).get("/health/memory")
        assert r.status_code == 200
        assert {"rss_mb", "peak_mb", "limit_mb", "steps", "skipped"} <= set(r.json())


# ------------------------------------------------------------ volume profile

ET = __import__("zoneinfo").ZoneInfo("America/New_York")
TODAY = datetime(2026, 11, 11, 11, 0, tzinfo=ET)


def _bars(sessions=6, base=1000.0):
    idx, vol = [], []
    day = TODAY.date()
    done = 0
    while done < sessions:
        day -= timedelta(days=1)
        if day.weekday() >= 5:
            continue
        done += 1
        t = datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET)
        while t.hour < 16:
            idx.append(t.astimezone(timezone.utc))
            vol.append(base)
            t += timedelta(minutes=5)
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": vol},
                        index=pd.DatetimeIndex(idx))


class _Redis:
    def __init__(self):
        self.store = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v):
        self.store[k] = v


class TestVolumeProfile:
    @pytest.fixture(autouse=True)
    def wire(self, monkeypatch):
        from src.scanner import spike_reversal as sr
        from src.data import client, redis_store
        self.sr = sr
        monkeypatch.setattr(sr, "_profile", {})
        monkeypatch.setattr(sr, "_profile_date", "")
        monkeypatch.setattr(sr, "_profile_failed_at", 0.0)
        self.redis = _Redis()
        monkeypatch.setattr(redis_store, "_get_redis", lambda: self.redis)
        self.calls = []
        self.fail = set()

        def fake_bars(symbols, timeframe=None, days=200):
            self.calls.append(list(symbols))
            if set(symbols) & self.fail:
                raise RuntimeError("alpaca error")
            return {s: _bars() for s in symbols}

        monkeypatch.setattr(client, "get_multi_bars", fake_bars)

    def syms(self, n):
        return [f"S{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(n)]

    def test_built_a_few_symbols_at_a_time(self):
        assert self.sr.ensure_volume_profile(self.syms(30), now=TODAY) is True
        assert all(len(c) <= self.sr._PROFILE_CHUNK for c in self.calls)
        assert sorted(s for c in self.calls for s in c) == sorted(self.syms(30))
        assert len(self.sr._profile) == 30 and self.sr._profile["SAA"]["09:30"] == 1000.0

    def test_second_call_the_same_day_fetches_nothing(self):
        self.sr.ensure_volume_profile(self.syms(10), now=TODAY)
        n = len(self.calls)
        assert self.sr.ensure_volume_profile(self.syms(10), now=TODAY) is True
        assert len(self.calls) == n

    def test_a_restart_loads_the_saved_profile_instead_of_rebuilding(self, monkeypatch):
        self.sr.ensure_volume_profile(self.syms(10), now=TODAY)
        monkeypatch.setattr(self.sr, "_profile", {})          # what a restart loses
        monkeypatch.setattr(self.sr, "_profile_date", "")
        self.calls.clear()
        assert self.sr.ensure_volume_profile(self.syms(10), now=TODAY) is True
        assert self.calls == [] and len(self.sr._profile) == 10

    def test_yesterdays_saved_profile_is_not_used(self, monkeypatch):
        self.sr.ensure_volume_profile(self.syms(4), now=TODAY - timedelta(days=1))
        monkeypatch.setattr(self.sr, "_profile", {})
        monkeypatch.setattr(self.sr, "_profile_date", "")
        self.calls.clear()
        self.sr.ensure_volume_profile(self.syms(4), now=TODAY)
        assert self.calls != []

    @pytest.mark.parametrize("junk", ["not json", '{"date": 5}', '[]', '{"date": "2026-11-11", "profile": 7}'])
    def test_unreadable_saved_profile_is_rebuilt(self, junk):
        self.redis.store[self.sr._PROFILE_KEY] = junk
        assert self.sr.ensure_volume_profile(self.syms(4), now=TODAY) is True
        assert self.calls != []

    def test_a_failed_piece_does_not_lose_the_rest(self):
        self.fail = {"SAA"}
        assert self.sr.ensure_volume_profile(self.syms(20), now=TODAY) is True
        first_chunk = self.syms(20)[:self.sr._PROFILE_CHUNK]          # the piece holding SAA
        assert not any(s in self.sr._profile for s in first_chunk)
        assert len(self.sr._profile) == 20 - self.sr._PROFILE_CHUNK

    def test_total_failure_waits_before_trying_again(self, monkeypatch):
        self.fail = set(self.syms(10))
        assert self.sr.ensure_volume_profile(self.syms(10), now=TODAY) is False
        n = len(self.calls)
        assert self.sr.ensure_volume_profile(self.syms(10), now=TODAY) is False
        assert len(self.calls) == n                           # no new heavy attempt yet
        monkeypatch.setattr(self.sr, "_profile_failed_at", time.time() - self.sr._PROFILE_RETRY - 1)
        self.fail = set()
        assert self.sr.ensure_volume_profile(self.syms(10), now=TODAY) is True

    def test_malformed_and_repeated_symbols_are_not_requested(self):
        self.sr.ensure_volume_profile(["SAA", "BRK-B", "SAA", "btc/usd", "SAB"], now=TODAY)
        assert sorted(s for c in self.calls for s in c) == ["SAA", "SAB"]

    def test_no_redis_still_builds(self, monkeypatch):
        from src.data import redis_store
        monkeypatch.setattr(redis_store, "_get_redis", lambda: None)
        assert self.sr.ensure_volume_profile(self.syms(4), now=TODAY) is True


class TestIntradayCacheDoesNotGrow:
    def test_expired_entries_are_dropped_on_write(self, monkeypatch):
        from src.data import client

        class Fake:
            def get_stock_bars(self, request):
                return type("R", (), {"df": pd.DataFrame()})()

        monkeypatch.setattr(client, "_get_data_client", lambda: Fake())
        monkeypatch.setattr(client, "_intraday_cache", {
            "old-1": (time.time() - 3600, {}),
            "old-2": (time.time() - client._INTRADAY_TTL_SECONDS, {}),
            "fresh": (time.time(), {}),
        })
        client.get_intraday_multi_bars(["AAPL"], minutes_back=60)
        assert "old-1" not in client._intraday_cache and "old-2" not in client._intraday_cache
        assert "fresh" in client._intraday_cache and len(client._intraday_cache) == 2
