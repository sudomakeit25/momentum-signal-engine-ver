"""Notification dispatcher: webhook (Discord/Telegram/Slack) + SMS (Twilio / Email Gateway)."""

import logging
import json
import smtplib
import threading
from dataclasses import dataclass
from email.mime.text import MIMEText
from pathlib import Path

import requests as http_requests

logger = logging.getLogger("mse.notifications")

# Persistent config file path (survives restarts on disk-based deploys)
_CONFIG_PATH = Path(".notification_config.json")
_config_lock = threading.Lock()

# Email-to-SMS carrier gateways (phone_number@gateway → delivers as SMS)
CARRIER_GATEWAYS: dict[str, str] = {
    "att": "txt.att.net",
    "tmobile": "tmomail.net",
    "verizon": "vtext.com",
    "sprint": "messaging.sprintpcs.com",
    "boost": "sms.myboostmobile.com",
    "cricket": "sms.cricketwireless.net",
    "metro": "mymetropcs.com",
    "uscellular": "email.uscc.net",
    "virgin": "vmobl.com",
    "google_fi": "msg.fi.google.com",
    "mint": "tmomail.net",
    "visible": "vtext.com",
    "xfinity": "vtext.com",
}


@dataclass
class NotificationConfig:
    """Notification preferences — saved to disk."""
    webhook_url: str = ""
    webhook_platform: str = "discord"  # discord | telegram | slack
    sms_to: str = ""  # recipient phone e.g. "+15559876543" or "5559876543"
    sms_method: str = "email_gateway"  # "twilio" | "email_gateway"
    sms_carrier: str = ""  # carrier key from CARRIER_GATEWAYS
    sms_consent: bool = False  # user opted in to receive SMS
    sms_consent_timestamp: str = ""  # ISO 8601 timestamp of consent
    auto_alerts_enabled: bool = False
    min_confidence: float = 0.6  # only alert on signals >= this confidence

    def to_dict(self) -> dict:
        return {
            "webhook_url": self.webhook_url,
            "webhook_platform": self.webhook_platform,
            "sms_to": self.sms_to,
            "sms_method": self.sms_method,
            "sms_carrier": self.sms_carrier,
            "sms_consent": self.sms_consent,
            "sms_consent_timestamp": self.sms_consent_timestamp,
            "auto_alerts_enabled": self.auto_alerts_enabled,
            "min_confidence": self.min_confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NotificationConfig":
        return cls(
            webhook_url=d.get("webhook_url", ""),
            webhook_platform=d.get("webhook_platform", "discord"),
            sms_to=d.get("sms_to", ""),
            sms_method=d.get("sms_method", "email_gateway"),
            sms_carrier=d.get("sms_carrier", ""),
            sms_consent=d.get("sms_consent", False),
            sms_consent_timestamp=d.get("sms_consent_timestamp", ""),
            auto_alerts_enabled=d.get("auto_alerts_enabled", False),
            min_confidence=d.get("min_confidence", 0.6),
        )


def load_config() -> NotificationConfig:
    """Load config from disk, or return defaults."""
    with _config_lock:
        if _CONFIG_PATH.exists():
            try:
                data = json.loads(_CONFIG_PATH.read_text())
                return NotificationConfig.from_dict(data)
            except Exception:
                pass
        return NotificationConfig()


def save_config(config: NotificationConfig) -> None:
    """Persist config to disk."""
    with _config_lock:
        _CONFIG_PATH.write_text(json.dumps(config.to_dict(), indent=2))


def send_webhook(url: str, platform: str, signals: list) -> bool:
    """Send signals to a webhook (Discord, Telegram, or Slack). Returns True on success."""
    if not url or not signals:
        return False

    try:
        if platform == "discord":
            fields = []
            for s in signals:
                emoji = "\U0001f7e2" if s.action.value == "BUY" else "\U0001f534"
                fields.append({
                    "name": f"{emoji} {s.symbol} — {s.action.value}",
                    "value": f"Entry: ${s.entry:.2f} | Conf: {s.confidence*100:.0f}% | R:R {s.rr_ratio:.1f}\n{s.reason[:100]}",
                    "inline": False,
                })
            payload = {"embeds": [{"title": "\U0001f514 MSE Signal Alert", "color": 3447003, "fields": fields}]}
            resp = http_requests.post(url, json=payload, timeout=10)
        elif platform == "telegram":
            lines = ["*\U0001f514 MSE Signal Alert*\n"]
            for s in signals:
                emoji = "\U0001f7e2" if s.action.value == "BUY" else "\U0001f534"
                lines.append(f"{emoji} *{s.symbol}* {s.action.value} @ ${s.entry:.2f} ({s.confidence*100:.0f}%)")
                lines.append(f"   R:R {s.rr_ratio:.1f} | {s.reason[:80]}")
            payload = {"text": "\n".join(lines), "parse_mode": "Markdown"}
            resp = http_requests.post(url, json=payload, timeout=10)
        else:
            # Slack or generic
            lines = ["\U0001f514 *MSE Signal Alert*\n"]
            for s in signals:
                emoji = ":green_circle:" if s.action.value == "BUY" else ":red_circle:"
                lines.append(f"{emoji} *{s.symbol}* {s.action.value} @ ${s.entry:.2f} ({s.confidence*100:.0f}%)")
            payload = {"text": "\n".join(lines)}
            resp = http_requests.post(url, json=payload, timeout=10)

        ok = 200 <= resp.status_code < 300
        if ok:
            logger.info("Webhook sent to %s: %d signals", platform, len(signals))
        else:
            logger.warning("Webhook failed (%s): HTTP %d", platform, resp.status_code)
        return ok
    except Exception as e:
        logger.warning("Webhook error (%s): %s", platform, e)
        return False


def _format_sms_body(signals: list) -> str:
    """Build a short SMS body. Carrier gateways cap at 160 chars."""
    lines = ["MSE Alert"]
    for s in signals:
        arrow = "+" if s.action.value == "BUY" else "-"
        line = f"{arrow}{s.symbol} {s.action.value} ${s.entry:.2f} {s.confidence*100:.0f}%"
        # Stop adding lines if we'd exceed 155 chars
        if len("\n".join(lines + [line])) > 155:
            break
        lines.append(line)
    return "\n".join(lines)


def send_email_sms(to_phone: str, carrier: str, signals: list) -> bool:
    """Send a single SMS via email-to-SMS carrier gateway (free, no Twilio).

    Sends one message with top signals that fit in 160 chars to avoid
    carrier rate-limiting on multiple rapid messages.
    """
    if not to_phone or not carrier or not signals:
        return False

    gateway = CARRIER_GATEWAYS.get(carrier)
    if not gateway:
        logger.warning("Email SMS skipped: unknown carrier '%s'", carrier)
        return False

    from config.settings import settings
    if not settings.smtp_email or not settings.smtp_password:
        logger.warning("Email SMS skipped: SMTP_EMAIL / SMTP_PASSWORD not configured")
        return False

    # Strip non-digit chars from phone number
    digits = "".join(c for c in to_phone if c.isdigit())
    # Remove leading country code '1' if 11 digits
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        logger.warning("Email SMS skipped: invalid phone number '%s'", to_phone)
        return False

    to_addr = f"{digits}@{gateway}"
    # Sort by confidence and send top signals that fit in one message
    sorted_signals = sorted(signals, key=lambda s: s.confidence, reverse=True)
    body = _format_sms_body(sorted_signals)

    try:
        msg = MIMEText(body)
        msg["From"] = settings.smtp_email
        msg["To"] = to_addr
        msg["Subject"] = ""

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.smtp_email, settings.smtp_password)
            server.send_message(msg)

        logger.info("Email SMS sent to %s via %s (%d chars)", to_addr, carrier, len(body))
        return True
    except Exception as e:
        logger.warning("Email SMS error: %s", e)
        return False


def send_sms(to_phone: str, signals: list) -> bool:
    """Send SMS alert via Twilio. Returns True on success."""
    if not to_phone or not signals:
        return False

    from config.settings import settings
    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_from_number:
        logger.warning("SMS skipped: Twilio credentials not configured")
        return False

    try:
        from twilio.rest import Client
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

        body = _format_sms_body(signals)

        message = client.messages.create(
            body=body,
            from_=settings.twilio_from_number,
            to=to_phone,
        )

        logger.info("SMS sent to %s: SID %s", to_phone, message.sid)
        return True
    except Exception as e:
        logger.warning("SMS error: %s", e)
        return False


def dispatch_alerts(signals: list) -> dict:
    """Send alerts through all enabled channels. Returns status per channel."""
    config = load_config()
    results = {"webhook": False, "sms": False}

    logger.info(
        "dispatch_alerts called: %d signals, auto_enabled=%s, sms_to=%s, sms_consent=%s, sms_method=%s, sms_carrier=%s, webhook_url=%s",
        len(signals), config.auto_alerts_enabled, config.sms_to,
        config.sms_consent, config.sms_method, config.sms_carrier,
        config.webhook_url[:30] + "..." if config.webhook_url else "",
    )

    if not config.auto_alerts_enabled:
        logger.info("Auto-alerts disabled, skipping dispatch")
        return results

    # Filter by minimum confidence
    filtered = [s for s in signals if s.confidence >= config.min_confidence]
    logger.info("After confidence filter (>= %.0f%%): %d of %d signals",
                config.min_confidence * 100, len(filtered), len(signals))
    if not filtered:
        return results

    if config.webhook_url:
        results["webhook"] = send_webhook(config.webhook_url, config.webhook_platform, filtered)

    if config.sms_to and config.sms_consent:
        if config.sms_method == "email_gateway" and config.sms_carrier:
            results["sms"] = send_email_sms(config.sms_to, config.sms_carrier, filtered)
        elif config.sms_method == "twilio":
            results["sms"] = send_sms(config.sms_to, filtered)
    elif config.sms_to and not config.sms_consent:
        logger.info("SMS skipped: consent not given")
    elif not config.sms_to:
        logger.info("SMS skipped: no phone number configured")

    return results
