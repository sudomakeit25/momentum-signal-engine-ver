"""Shared test setup.

Telegram credentials are blanked for every test, so a TELEGRAM_BOT_TOKEN in a
local .env can never make the suite post to a real chat. Tests that exercise
Telegram set their own fake credentials and a fake HTTP client.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_real_telegram(monkeypatch):
    from config.settings import settings
    from src.notifications import dispatcher
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    monkeypatch.setattr(dispatcher, "_tg_pending", [])
