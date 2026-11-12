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
def _no_real_telegram(monkeypatch):
    from config.settings import settings
    from src.notifications import dispatcher
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    monkeypatch.setattr(dispatcher, "_tg_pending", [])
