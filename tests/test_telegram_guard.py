"""The suite must never post to a real Telegram chat, even when a real bot
token sits in a local .env (tests/conftest.py blanks it for every test)."""

from datetime import datetime, timezone

from config.settings import settings
from src.data.models import IntradayWatch
from src.notifications import dispatcher, telegram


def test_credentials_are_blank_inside_tests():
    assert settings.telegram_bot_token == "" and settings.telegram_chat_id == ""
    assert telegram.configured() is False


def test_dispatch_with_alerts_on_makes_no_telegram_request(monkeypatch):
    # Mirrors the intraday-movers watch tests that run with alerts enabled.
    calls = []
    monkeypatch.setattr(telegram.requests, "post", lambda *a, **k: calls.append(a) or None)
    monkeypatch.setattr(dispatcher, "load_config",
                        lambda: dispatcher.NotificationConfig(auto_alerts_enabled=True))
    monkeypatch.setattr(dispatcher, "_recent_sms_fingerprints", lambda: {})
    import src.data.redis_store as rs
    monkeypatch.setattr(rs, "get_push_tokens", lambda: {})
    watch = IntradayWatch(symbol="SNDK", watch_type="box_forming", detail="d", upper=890.0,
                          lower=884.0, timestamp=datetime(2026, 11, 11, 15, tzinfo=timezone.utc))
    assert dispatcher.dispatch_intraday_watches([watch])["telegram"] is False
    assert calls == [] and dispatcher.telegram_pending() == 0
