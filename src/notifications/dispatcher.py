"""Notification dispatcher: webhook (Discord/Telegram/Slack) + SMS (Twilio / Email Gateway)."""

import hashlib
import logging
import json
import smtplib
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

import requests as http_requests

logger = logging.getLogger("mse.notifications")

_SMS_FINGERPRINT_KEY = "mse:sms_fingerprints"  # { hash: iso_ts } — 30m TTL
_SMS_FINGERPRINT_TTL = 30 * 60  # seconds


def _deduped_signals_for_sms(signals: list) -> list:
    """Collapse same symbol:action:setup to the single highest-confidence signal.

    A secondary defense against the signal generator occasionally emitting
    multiple variants of the same setup (which was filling SMS bodies with
    duplicate rows like '+PFE BUY 70%' and '+PFE BUY 60%').
    """
    by_key: dict[str, object] = {}
    for s in signals:
        try:
            setup = s.setup_type.value if hasattr(s.setup_type, "value") else str(s.setup_type)
        except Exception:
            setup = ""
        key = f"{s.symbol}:{s.action.value}:{setup}"
        existing = by_key.get(key)
        if existing is None or getattr(s, "confidence", 0) > getattr(existing, "confidence", 0):
            by_key[key] = s
    return list(by_key.values())


def _recent_sms_fingerprints() -> dict[str, str]:
    """Load the recent-SMS fingerprint map from Redis."""
    try:
        from src.data.redis_store import _get_redis
        redis = _get_redis()
        if not redis:
            return {}
        raw = redis.get(_SMS_FINGERPRINT_KEY)
        if not raw:
            return {}
        data = json.loads(raw) if isinstance(raw, str) else raw
        # Prune expired
        now = datetime.now(timezone.utc)
        fresh = {
            h: ts for h, ts in (data or {}).items()
            if (now - datetime.fromisoformat(ts)).total_seconds() < _SMS_FINGERPRINT_TTL
        }
        return fresh
    except Exception as e:
        logger.debug("Fingerprint load failed: %s", e)
        return {}


def _record_sms_fingerprint(fingerprint: str) -> None:
    """Mark a fingerprint as just-sent, for the 30-minute window."""
    try:
        from src.data.redis_store import _get_redis
        redis = _get_redis()
        if not redis:
            return
        data = _recent_sms_fingerprints()
        data[fingerprint] = datetime.now(timezone.utc).isoformat()
        redis.set(_SMS_FINGERPRINT_KEY, json.dumps(data))
    except Exception as e:
        logger.debug("Fingerprint save failed: %s", e)


def _fingerprint_of_body(body: str) -> str:
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()[:16]

# File-based fallback for local dev
_CONFIG_PATH = Path(".notification_config.json")
_config_lock = threading.Lock()

# Redis key for notification config
_REDIS_KEY = "mse:notification_config"


def _get_redis():
    """Get Upstash Redis client, or None if not configured."""
    from config.settings import settings
    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        try:
            from upstash_redis import Redis
            return Redis(
                url=settings.upstash_redis_rest_url,
                token=settings.upstash_redis_rest_token,
            )
        except Exception as e:
            logger.warning("Redis connection failed, falling back to file: %s", e)
    return None

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
    """Load config from Redis (preferred) or disk fallback."""
    redis = _get_redis()
    if redis:
        try:
            data = redis.get(_REDIS_KEY)
            if data:
                if isinstance(data, str):
                    data = json.loads(data)
                return NotificationConfig.from_dict(data)
        except Exception as e:
            logger.warning("Redis load failed, falling back to file: %s", e)

    with _config_lock:
        if _CONFIG_PATH.exists():
            try:
                data = json.loads(_CONFIG_PATH.read_text())
                return NotificationConfig.from_dict(data)
            except Exception:
                pass
    return NotificationConfig()


def save_config(config: NotificationConfig) -> None:
    """Persist config to Redis (preferred) and disk fallback."""
    config_json = json.dumps(config.to_dict(), indent=2)

    redis = _get_redis()
    if redis:
        try:
            redis.set(_REDIS_KEY, config_json)
            logger.info("Notification config saved to Redis")
        except Exception as e:
            logger.warning("Redis save failed, falling back to file: %s", e)

    with _config_lock:
        _CONFIG_PATH.write_text(config_json)


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
    """Build a short SMS body. Carrier gateways cap at 160 chars.

    Dedupes signals by (symbol, action, setup_type) and keeps the highest-
    confidence variant so the body never contains the same setup twice.
    """
    deduped = _deduped_signals_for_sms(signals)
    deduped.sort(key=lambda s: getattr(s, "confidence", 0), reverse=True)
    lines = ["MSE Alert"]
    for s in deduped:
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
    body = _format_sms_body(signals)

    # Fingerprint check — if we sent the exact same body in the last 30 min
    # (any cause: restart, double-cycle, parallel worker), silently skip.
    fp = _fingerprint_of_body(body)
    recent = _recent_sms_fingerprints()
    if fp in recent:
        logger.info("Email SMS suppressed (duplicate body sent %s)", recent[fp])
        return False

    try:
        msg = MIMEText(body)
        msg["From"] = settings.smtp_email
        msg["To"] = to_addr
        msg["Subject"] = ""

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.smtp_email, settings.smtp_password)
            server.send_message(msg)

        _record_sms_fingerprint(fp)
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

        fp = _fingerprint_of_body(body)
        recent = _recent_sms_fingerprints()
        if fp in recent:
            logger.info("Twilio SMS suppressed (duplicate body sent %s)", recent[fp])
            return False

        message = client.messages.create(
            body=body,
            from_=settings.twilio_from_number,
            to=to_phone,
        )

        _record_sms_fingerprint(fp)
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

    # Log alerts to history
    try:
        from src.data.redis_store import log_alert
        for s in filtered:
            log_alert({
                "symbol": s.symbol,
                "action": s.action.value,
                "setup_type": s.setup_type.value if hasattr(s.setup_type, 'value') else str(s.setup_type),
                "entry": s.entry,
                "confidence": s.confidence,
                "reason": s.reason[:100],
                "sms_sent": results["sms"],
                "webhook_sent": results["webhook"],
            })
    except Exception as e:
        logger.debug("Alert history logging failed: %s", e)

    return results
