"""Tests for the Redis-backed seen-signal dedup store."""

import json

from src.data import redis_store


class _FakeRedis:
    """Minimal in-memory stand-in for upstash_redis.Redis."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def test_save_and_load_roundtrip(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(redis_store, "_get_redis", lambda: fake)

    keys = {"AAPL:BUY:breakout", "MSFT:BUY:pullback"}
    assert redis_store.save_seen_signals(keys, "2026-04-19") is True

    loaded, date = redis_store.load_seen_signals()
    assert loaded == keys
    assert date == "2026-04-19"


def test_load_no_redis_returns_empty(monkeypatch):
    monkeypatch.setattr(redis_store, "_get_redis", lambda: None)
    keys, date = redis_store.load_seen_signals()
    assert keys == set()
    assert date == ""


def test_save_no_redis_noop(monkeypatch):
    monkeypatch.setattr(redis_store, "_get_redis", lambda: None)
    assert redis_store.save_seen_signals({"X"}, "2026-04-19") is False


def test_load_handles_legacy_list(monkeypatch):
    """Old persisted shape may be a JSON list — confirm we still parse it."""
    fake = _FakeRedis()
    fake.store["mse:seen_signals"] = json.dumps(["AAPL:BUY:breakout"])
    fake.store["mse:seen_signals_date"] = "2026-04-18"
    monkeypatch.setattr(redis_store, "_get_redis", lambda: fake)

    keys, date = redis_store.load_seen_signals()
    assert keys == {"AAPL:BUY:breakout"}
    assert date == "2026-04-18"
