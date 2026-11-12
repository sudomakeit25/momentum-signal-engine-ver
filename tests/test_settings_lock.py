"""Alert settings and test messages need the settings key. They were open to
anyone: the saved phone number could be read, alerts switched off, and the
server made to send texts, emails or webhook posts to any address."""

import pytest
import requests

from src.api import routes
from src.notifications import dispatcher

KEY = "correct-horse-battery-staple"


@pytest.fixture
def store(monkeypatch):
    saved = {"cfg": dispatcher.NotificationConfig(
        sms_to="+15551234567", sms_method="email_gateway", sms_carrier="tmobile", sms_consent=True,
        webhook_url="https://api.telegram.org/bot123456:SECRETTOKEN/sendMessage?chat_id=9",
        webhook_platform="telegram", auto_alerts_enabled=True, min_confidence=0.55)}
    monkeypatch.setattr(routes, "load_notification_config", lambda: saved["cfg"])
    monkeypatch.setattr(routes, "save_notification_config", lambda c: saved.__setitem__("cfg", c))
    monkeypatch.setattr(routes.settings if hasattr(routes, "settings") else __import__("config.settings", fromlist=["settings"]).settings,
                        "settings_key", KEY)
    return saved


@pytest.fixture
def client(store):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


@pytest.fixture
def outbound(monkeypatch):
    """Every way these endpoints could send something; records instead."""
    calls = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: calls.append(("post", a, k)) or
                        type("R", (), {"status_code": 200, "json": lambda self: {}})())
    monkeypatch.setattr(routes, "send_email_sms", lambda to, carrier, s: calls.append(("sms", to)) or True)
    monkeypatch.setattr(routes, "send_sms", lambda to, s: calls.append(("twilio", to)) or True)
    monkeypatch.setattr(routes, "send_telegram", lambda *a: calls.append(("telegram", a)) or True)
    monkeypatch.setattr(routes, "send_discord", lambda *a: calls.append(("discord", a)) or True)
    monkeypatch.setattr(routes, "send_email_digest", lambda *a: calls.append(("digest", a)) or True)
    from src.data import client as data_client

    def no_scan(*a, **k):
        raise AssertionError("a refused request must not scan")

    monkeypatch.setattr(data_client, "get_multi_bars", no_scan)
    return calls


def _set_key(value):
    from config.settings import settings
    settings.settings_key = value


H = {"X-Settings-Key": KEY}


class TestReadingSettings:
    def test_without_the_key_the_number_and_webhook_are_hidden(self, client):
        body = client.get("/notifications/config").json()
        assert body["masked"] is True
        assert body["sms_to"] == "•••••••67" and "5551234567" not in str(body)
        assert body["webhook_url"] == "https://api.telegram.org/…" and "SECRETTOKEN" not in str(body)
        assert body["auto_alerts_enabled"] is True and body["sms_carrier"] == "tmobile"

    def test_with_the_key_they_are_shown(self, client):
        body = client.get("/notifications/config", headers=H).json()
        assert body["masked"] is False and body["sms_to"] == "+15551234567"
        assert "SECRETTOKEN" in body["webhook_url"]

    @pytest.mark.parametrize("headers", [{"X-Settings-Key": "wrong-key-of-enough-length"}, {}])
    def test_wrong_or_missing_key_stays_hidden(self, client, headers):
        assert client.get("/notifications/config", headers=headers).json()["masked"] is True

    def test_empty_values_stay_empty(self, client, store):
        store["cfg"] = dispatcher.NotificationConfig()
        body = client.get("/notifications/config").json()
        assert body["sms_to"] == "" and body["webhook_url"] == ""


class TestChangingSettings:
    def _post(self, client, headers=None, **params):
        base = {"sms_to": "•••••••67", "webhook_url": "https://api.telegram.org/…",
                "sms_carrier": "tmobile", "sms_consent": "true", "auto_alerts_enabled": "false"}
        return client.post("/notifications/config", params={**base, **params}, headers=headers or {})

    def test_refused_while_no_key_is_set_on_the_server(self, client, store, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "settings_key", "")
        r = self._post(client, H)
        assert r.status_code == 403 and "SETTINGS_KEY" in r.json()["detail"]
        assert store["cfg"].auto_alerts_enabled is True          # unchanged

    def test_a_short_server_key_does_not_count(self, client, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "settings_key", "short")
        assert self._post(client, {"X-Settings-Key": "short"}).status_code == 403

    @pytest.mark.parametrize("headers", [{}, {"X-Settings-Key": "wrong-key-of-enough-length"},
                                         {"X-Settings-Key": KEY + " "}])
    def test_wrong_or_missing_key_changes_nothing(self, client, store, headers):
        r = self._post(client, headers)
        assert r.status_code == 403 and store["cfg"].auto_alerts_enabled is True

    def test_right_key_saves_and_the_reply_hides_the_number(self, client, store):
        r = self._post(client, H)
        assert r.status_code == 200 and r.json()["status"] == "saved"
        assert store["cfg"].auto_alerts_enabled is False
        assert "5551234567" not in r.text and "SECRETTOKEN" not in r.text

    def test_hidden_values_sent_back_keep_the_saved_ones(self, client, store):
        self._post(client, H)
        assert store["cfg"].sms_to == "+15551234567"
        assert "SECRETTOKEN" in store["cfg"].webhook_url

    def test_new_values_replace_them(self, client, store):
        self._post(client, H, sms_to="5559998888", webhook_url="https://discord.com/api/webhooks/1/x")
        assert store["cfg"].sms_to == "5559998888"
        assert store["cfg"].webhook_url == "https://discord.com/api/webhooks/1/x"


SENDERS = [
    ("/notifications/test-sms", {"to": "5550001111"}),
    ("/webhook/test", {"url": "https://example.com/hook"}),
    ("/webhook/notify", {"url": "https://example.com/hook"}),
    ("/notifications/test-telegram", {"bot_token": "1:x", "chat_id": "2"}),
    ("/notifications/test-discord", {"webhook_url": "https://example.com/hook"}),
    ("/notifications/send-digest", {"to_email": "someone@example.com"}),
]


class TestSending:
    @pytest.mark.parametrize("path,params", SENDERS)
    def test_refused_without_the_key_and_nothing_is_sent(self, client, outbound, path, params):
        r = client.post(path, params=params)
        assert r.status_code == 403 and outbound == []

    @pytest.mark.parametrize("path,params", [s for s in SENDERS if s[0] != "/webhook/notify"])
    def test_allowed_with_the_key(self, client, outbound, path, params):
        r = client.post(path, params=params, headers=H)
        assert r.status_code == 200 and outbound

    def test_test_text_with_the_hidden_number_goes_to_the_saved_number(self, client, outbound):
        client.post("/notifications/test-sms", params={"to": "•••••••67"}, headers=H)
        assert ("sms", "+15551234567") in outbound

    def test_webhook_test_with_the_hidden_address_uses_the_saved_one(self, client, outbound):
        client.post("/webhook/test", params={"url": "https://api.telegram.org/…", "platform": "telegram"},
                    headers=H)
        assert any(c[0] == "post" and "SECRETTOKEN" in c[1][0] for c in outbound)

    def test_new_telegram_test_stays_open(self, client, monkeypatch):
        # Fixed text to the configured chat, once a minute: harmless without a key.
        r = client.post("/notifications/telegram/test")
        assert r.status_code == 200


class TestLogs:
    def test_alerts_do_not_write_the_number_or_webhook_to_the_logs(self, store, monkeypatch, mse_logs):
        caplog = mse_logs
        from datetime import datetime, timezone
        from src.data.models import Signal, SignalAction, SetupType
        monkeypatch.setattr(dispatcher, "load_config", lambda: store["cfg"])
        monkeypatch.setattr(dispatcher, "send_email_sms", lambda *a, **k: False)
        monkeypatch.setattr(dispatcher, "send_webhook", lambda *a, **k: False)
        import src.data.redis_store as rs
        monkeypatch.setattr(rs, "get_push_tokens", lambda: {})
        monkeypatch.setattr(rs, "log_alert", lambda *a, **k: None)
        s = Signal(symbol="NVDA", action=SignalAction.BUY, setup_type=SetupType.BREAKOUT, reason="r",
                   entry=100, stop_loss=95, target=110, rr_ratio=2, confidence=0.9,
                   timestamp=datetime(2026, 11, 12, 15, tzinfo=timezone.utc))
        dispatcher.dispatch_alerts([s])
        assert "dispatch_alerts called" in caplog.text            # the log was really captured
        assert "5551234567" not in caplog.text and "SECRETTOKEN" not in caplog.text
        assert "ends 67" in caplog.text
