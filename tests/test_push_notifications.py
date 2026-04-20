"""Tests for Expo push: token store + dispatcher integration."""

import json

from src.data import redis_store
from src.notifications import dispatcher


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


class _Signal:
    """Minimal signal stand-in matching the attributes the dispatcher reads."""

    class _A:
        def __init__(self, v):
            self.value = v

    class _ST:
        def __init__(self, v):
            self.value = v

    def __init__(self, sym, action, setup, entry, conf):
        self.symbol = sym
        self.action = self._A(action)
        self.setup_type = self._ST(setup)
        self.entry = entry
        self.confidence = conf


class TestTokenStore:
    def test_add_valid_token(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(redis_store, "_get_redis", lambda: fake)
        ok = redis_store.add_push_token("ExponentPushToken[abc123]", "ios")
        assert ok is True
        tokens = redis_store.get_push_tokens()
        assert "ExponentPushToken[abc123]" in tokens
        assert tokens["ExponentPushToken[abc123]"]["platform"] == "ios"

    def test_reject_invalid_token(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(redis_store, "_get_redis", lambda: fake)
        assert redis_store.add_push_token("not-an-expo-token") is False
        assert redis_store.get_push_tokens() == {}

    def test_remove_token(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(redis_store, "_get_redis", lambda: fake)
        redis_store.add_push_token("ExponentPushToken[x]", "android")
        assert redis_store.remove_push_token("ExponentPushToken[x]") is True
        assert redis_store.get_push_tokens() == {}

    def test_no_redis_returns_empty(self, monkeypatch):
        monkeypatch.setattr(redis_store, "_get_redis", lambda: None)
        assert redis_store.get_push_tokens() == {}
        assert redis_store.add_push_token("ExponentPushToken[x]") is False


class TestExpoPushSend:
    def test_empty_tokens_returns_false(self):
        assert dispatcher.send_expo_push([], [_Signal("AAPL", "BUY", "brk", 200, 0.8)]) is False

    def test_empty_signals_returns_false(self):
        assert dispatcher.send_expo_push(["ExponentPushToken[x]"], []) is False

    def test_posts_to_expo_and_suppresses_duplicate(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(redis_store, "_get_redis", lambda: fake)
        # Also patch the dispatcher's _get_redis (different module)
        from src.data.redis_store import _get_redis as real
        monkeypatch.setattr("src.data.redis_store._get_redis", lambda: fake)

        calls: list[dict] = []

        class _Resp:
            status_code = 200
            text = ""

        def _fake_post(url, json=None, headers=None, timeout=None):
            calls.append({"url": url, "json": json})
            return _Resp()

        monkeypatch.setattr(dispatcher.http_requests, "post", _fake_post)

        sigs = [_Signal("AAPL", "BUY", "brk", 200.0, 0.8)]
        ok1 = dispatcher.send_expo_push(["ExponentPushToken[x]"], sigs)
        ok2 = dispatcher.send_expo_push(["ExponentPushToken[x]"], sigs)
        assert ok1 is True
        # Second call with same body is suppressed by the fingerprint window.
        assert ok2 is False
        assert len(calls) == 1
        # Body format sanity
        msg = calls[0]["json"][0]
        assert msg["to"] == "ExponentPushToken[x]"
        assert "AAPL" in msg["body"]

    def test_propagates_http_failure(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(redis_store, "_get_redis", lambda: fake)
        monkeypatch.setattr("src.data.redis_store._get_redis", lambda: fake)

        class _Resp:
            status_code = 400
            text = "bad request"

        monkeypatch.setattr(
            dispatcher.http_requests, "post",
            lambda *a, **kw: _Resp(),
        )
        ok = dispatcher.send_expo_push(
            ["ExponentPushToken[x]"],
            [_Signal("AAPL", "BUY", "brk", 200.0, 0.8)],
        )
        assert ok is False
