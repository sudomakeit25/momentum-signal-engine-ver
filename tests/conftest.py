"""Shared test setup.

Telegram credentials are blanked for every test, so a TELEGRAM_BOT_TOKEN in a
local .env can never make the suite post to a real chat. Tests that exercise
Telegram set their own fake credentials and a fake HTTP client.
"""

import pytest


@pytest.fixture
def mse_logs(caplog):
    """caplog for the app's own loggers. src/main.py stops "mse" and
    "mse.notifications" from propagating to the root logger, where caplog
    listens, so without this a test that checks something is NOT logged
    passes without seeing any log at all. Pair every absence check with a
    presence check."""
    import logging
    loggers = [logging.getLogger(n) for n in ("mse", "mse.notifications")]
    levels = [lg.level for lg in loggers]
    for lg in loggers:
        lg.addHandler(caplog.handler)
        lg.setLevel(logging.DEBUG)
    caplog.set_level(logging.DEBUG)
    try:
        yield caplog
    finally:
        for lg, level in zip(loggers, levels):
            lg.removeHandler(caplog.handler)
            lg.setLevel(level)


@pytest.fixture(autouse=True)
def _no_real_most_actives(monkeypatch):
    """The movers screen adds Alpaca's most-active list; no test may fetch
    it for real. Tests of that list replace _fetch themselves."""
    from src.data import most_actives
    monkeypatch.setattr(most_actives, "_fetch", lambda top: [])
    monkeypatch.setattr(most_actives, "_cache", {"at": 0.0, "symbols": [], "failed_at": 0.0})


@pytest.fixture(autouse=True)
def _no_real_telegram(monkeypatch):
    from config.settings import settings
    from src.notifications import dispatcher
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    monkeypatch.setattr(dispatcher, "_tg_pending", [])


@pytest.fixture(autouse=True)
def _no_real_redis(monkeypatch):
    """A local .env may hold the production Upstash address; no test may
    read or write it. Code then uses its in-memory fallbacks."""
    from config.settings import settings
    monkeypatch.setattr(settings, "upstash_redis_rest_url", "")
    monkeypatch.setattr(settings, "upstash_redis_rest_token", "")


@pytest.fixture(autouse=True)
def _fresh_map_record(monkeypatch):
    """The probability map's live record keeps module state; start each test clean."""
    from src.scanner import map_record
    monkeypatch.setattr(map_record, "_mem", {})
    monkeypatch.setattr(map_record, "_failed_at", 0.0)
    monkeypatch.setattr(map_record, "_done_for", None)
    monkeypatch.setattr(map_record, "_report_cache", None)


@pytest.fixture(autouse=True)
def _no_real_sms(monkeypatch, tmp_path):
    """A local .env may hold real Gmail, Twilio or Brevo credentials, and
    .notification_config.json the owner's phone number; no test may text
    anyone. Tests of the SMS path set fakes themselves."""
    from config.settings import settings
    from src.notifications import dispatcher
    for name in ("smtp_email", "smtp_password", "twilio_account_sid", "twilio_auth_token",
                 "twilio_from_number", "brevo_api_key", "brevo_sender_email"):
        monkeypatch.setattr(settings, name, "")
    monkeypatch.setattr(dispatcher, "_CONFIG_PATH", tmp_path / "no_notification_config.json")


@pytest.fixture(autouse=True)
def _fresh_map_alerts(monkeypatch):
    """The probability map alerts keep module state; start each test clean."""
    from src.notifications import map_alerts
    monkeypatch.setattr(map_alerts, "_mem", {})
    monkeypatch.setattr(map_alerts, "_digest_done_for", None)
    monkeypatch.setattr(map_alerts, "_open_done", {})
    monkeypatch.setattr(map_alerts, "_closes", {})
    # No calendar lookups over the network in tests: a normal 16:00 close
    # unless a test sets its own.
    from datetime import time as _t
    monkeypatch.setattr(map_alerts, "session_close", lambda day: _t(16, 0))
