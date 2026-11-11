"""Notification dispatcher: webhook (Discord/Telegram/Slack) + SMS (Twilio / Email Gateway)."""

import contextlib
import contextvars
import hashlib
import logging
import json
import smtplib
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import requests as http_requests

logger = logging.getLogger("mse.notifications")
_ET = ZoneInfo("America/New_York")

_SMS_FINGERPRINT_KEY = "mse:sms_fingerprints"  # { hash: iso_ts } — 30m TTL
_SMS_FINGERPRINT_TTL = 30 * 60  # seconds


def _deduped_signals_for_sms(signals: list) -> list:
    """Collapse same symbol:action to the single highest-confidence signal.

    The generator emits the same symbol/action across several setup types
    (EMA_CROSSOVER, BREAKOUT, RSI_PULLBACK, VWAP_RECLAIM). Since the SMS
    body for each variant is identical to the user (+SYM ACTION $PRICE %),
    keying dedup by setup as well surfaced duplicate rows. Key by
    symbol:action and keep the highest-confidence variant so the SMS
    reflects the strongest trigger.
    """
    by_key: dict[str, object] = {}
    for s in signals:
        key = f"{s.symbol}:{s.action.value}"
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


_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


# Suffix for alert headers, set by the caller for the duration of a dispatch
# (for example " (15m delayed)"). A ContextVar so the scan loops, which run
# on separate threads, cannot leak a label into each other's messages.
_header_suffix: contextvars.ContextVar[str] = contextvars.ContextVar("mse_header_suffix", default="")


@contextlib.contextmanager
def alert_label(suffix: str):
    """Append `suffix` to the header of every alert formatted inside."""
    token = _header_suffix.set(suffix or "")
    try:
        yield
    finally:
        _header_suffix.reset(token)


def _intraday_arrow(pattern_type: str) -> str:
    """Compact glyph for SMS / push body lines."""
    return {
        "v_reversal": "V↑",
        "inverted_v": "Λ↓",
        "breakdown": "↓",
        "breakout": "↑",
    }.get(pattern_type, "")


def _format_intraday_body(
    patterns: list, header: str | None = None, limit: int = 5, show_more: bool = False
) -> str:
    """Build a short body for SMS / push from intraday patterns. SMS and push
    keep the first 5; Telegram passes a larger `limit` and `show_more` so
    nothing is silently cut."""
    if not patterns:
        return ""
    if header is None:
        header = (
            "MSE Intraday"
            if len(patterns) == 1
            else f"MSE Intraday: {len(patterns)} patterns"
        )
    lines = [header + _header_suffix.get()]
    for p in patterns[:limit]:
        glyph = _intraday_arrow(p.pattern_type)
        lines.append(
            f"{glyph} {p.symbol} ${p.trigger_price:.2f} ({p.move_pct:+.1f}%/{p.recovery_pct:+.1f}%)"
        )
    if show_more and len(patterns) > limit:
        lines.append(f"and {len(patterns) - limit} more")
    return "\n".join(lines)


def send_expo_push_intraday(tokens: list[str], patterns: list) -> bool:
    """Push notification for intraday patterns. Mirrors send_expo_push
    structure but uses an intraday-specific title and deep-links the
    top-priority pattern's symbol."""
    if not tokens or not patterns:
        return False
    body = _format_intraday_body(patterns, header=None)
    fp = _fingerprint_of_body(f"intraday_push:{body}")
    recent = _recent_sms_fingerprints()
    if fp in recent:
        logger.info("Intraday push suppressed (duplicate body sent %s)", recent[fp])
        return False

    title = (
        "MSE Intraday Pattern"
        if len(patterns) == 1
        else f"MSE Intraday: {len(patterns)} patterns"
    )
    messages = [
        {
            "to": t,
            "sound": "default",
            "title": title,
            "body": body,
            "data": {
                "type": "intraday_pattern",
                "url": f"mse://instrument/{patterns[0].symbol}",
            },
        }
        for t in tokens
    ]
    try:
        resp = http_requests.post(
            _EXPO_PUSH_URL,
            json=messages,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=10,
        )
        ok = 200 <= resp.status_code < 300
        if ok:
            _record_sms_fingerprint(fp)
            logger.info("Intraday push sent to %d tokens (%d chars)", len(tokens), len(body))
        else:
            logger.warning("Intraday push failed: HTTP %d: %s", resp.status_code, resp.text[:200])
        return ok
    except Exception as e:
        logger.warning("Intraday push error: %s", e)
        return False


_SMTP_TIMEOUT = 15  # seconds; without one a blocked mail port stalls the scan loop for minutes


def _format_telegram_signals(signals: list, limit: int = 10) -> str:
    """Telegram body for trade signals. No 160-character cap, so each signal
    carries its levels: entry, stop, target, reward to risk, and the reason."""
    deduped = _deduped_signals_for_sms(signals)
    deduped.sort(key=lambda s: getattr(s, "confidence", 0), reverse=True)
    if not deduped:
        return ""
    lines = ["MSE Alert" + _header_suffix.get()]
    for s in deduped[:limit]:
        setup = s.setup_type.value if hasattr(s.setup_type, "value") else str(s.setup_type)
        lines.append("")
        lines.append(f"{s.action.value} {s.symbol}  {setup.replace('_', ' ')}  {s.confidence * 100:.0f}%")
        lines.append(f"entry ${s.entry:.2f} | stop ${s.stop_loss:.2f} | target ${s.target:.2f} | R:R {s.rr_ratio:.1f}")
        if s.reason:
            lines.append(s.reason[:160])
    if len(deduped) > limit:
        lines.append("")
        lines.append(f"and {len(deduped) - limit} more")
    return "\n".join(lines)


# Telegram sends that failed. The scan loops mark an alert as seen whether or
# not it was delivered, so without this queue a Telegram outage at the moment
# an alert fires would lose it for good. `retry_failed_telegram` is called
# from the intraday loop every few minutes. Alerts older than the age limit
# are dropped: on delayed data they are stale by then.
_TG_PENDING_MAX = 20
_TG_PENDING_MAX_AGE = 30 * 60  # seconds
_tg_pending: list[dict] = []
_tg_lock = threading.Lock()


def _queue_telegram(kind: str, body: str, fp: str) -> None:
    with _tg_lock:
        if any(item["fp"] == fp for item in _tg_pending):
            return
        _tg_pending.append({"kind": kind, "body": body, "fp": fp, "first": time.time()})
        dropped = len(_tg_pending) - _TG_PENDING_MAX
        if dropped > 0:
            del _tg_pending[:dropped]
    if dropped > 0:
        logger.warning("Telegram retry queue full: dropped %d oldest alerts", dropped)
    logger.info("Telegram %s alert queued for retry", kind)


def telegram_pending() -> int:
    with _tg_lock:
        return len(_tg_pending)


def retry_failed_telegram(now: float | None = None) -> int:
    """Resend queued Telegram alerts, oldest first. Stops at the first failure
    so a Telegram outage costs one request per call, not one per alert.
    Returns how many were delivered. Never raises."""
    try:
        from src.notifications import telegram
        now = time.time() if now is None else now
        with _tg_lock:
            fresh = [i for i in _tg_pending if now - i["first"] <= _TG_PENDING_MAX_AGE]
            expired = len(_tg_pending) - len(fresh)
            _tg_pending[:] = fresh
            batch = list(fresh)
        if expired:
            logger.warning("Telegram retry: dropped %d alerts older than %d minutes",
                           expired, _TG_PENDING_MAX_AGE // 60)
        if not batch or not telegram.configured():
            return 0
        delivered = 0
        for item in batch:
            first = datetime.fromtimestamp(item["first"], tz=_ET).strftime("%H:%M")
            if not telegram.send_text(f"{item['body']}\n\n(late: first attempt at {first} ET failed)"):
                break
            _record_sms_fingerprint(item["fp"])
            delivered += 1
            with _tg_lock:
                _tg_pending[:] = [i for i in _tg_pending if i is not item]
        if delivered:
            logger.info("Telegram retry: delivered %d queued alerts", delivered)
        return delivered
    except Exception as e:
        logger.warning("Telegram retry failed: %s", type(e).__name__)
        return 0


def _send_telegram(kind: str, body: str) -> bool:
    """Send an alert body to Telegram when a bot is configured. Uses the same
    30-minute duplicate guard as SMS, keyed separately. A failed send is
    queued for `retry_failed_telegram`. Never raises."""
    fp = None
    try:
        from src.notifications import telegram
        if not body or not telegram.configured():
            return False
        fp = _fingerprint_of_body(f"telegram:{kind}:{body}")
        recent = _recent_sms_fingerprints()
        if fp in recent:
            logger.info("Telegram %s alert suppressed (duplicate body sent %s)", kind, recent[fp])
            return False
        if telegram.send_text(body):
            _record_sms_fingerprint(fp)
            return True
    except Exception as e:
        logger.warning("Telegram %s dispatch failed: %s", kind, type(e).__name__)
    if fp is not None:
        _queue_telegram(kind, body, fp)
    return False


def dispatch_intraday_patterns(patterns: list) -> dict:
    """Route detected intraday patterns to Telegram + SMS + push.

    Distinct from `dispatch_alerts` because the dedup grain differs:
    intraday patterns are keyed by (symbol, pattern_type, trading_day)
    so a V-reversal and a later breakdown on the same symbol can both
    fire once. Reuses the same SMS / push primitives for delivery and
    the same 30-min body fingerprint as a final spam guard.
    """
    results = {"sms": False, "push": False, "telegram": False}
    if not patterns:
        return results

    config = load_config()
    if not config.auto_alerts_enabled:
        logger.info("Intraday auto-alerts disabled, skipping dispatch")
        return results

    # Telegram first: it is the quick channel, and a slow SMS attempt must not delay it.
    results["telegram"] = _send_telegram(
        "intraday", _format_intraday_body(patterns, limit=30, show_more=True))

    if config.sms_to and config.sms_consent:
        body = _format_intraday_body(patterns)
        fp = _fingerprint_of_body(f"intraday_sms:{body}")
        recent = _recent_sms_fingerprints()
        if fp in recent:
            logger.info("Intraday SMS suppressed (duplicate body sent %s)", recent[fp])
        else:
            try:
                if config.sms_method == "email_gateway" and config.sms_carrier:
                    # Reuse the email-gateway send by feeding it a
                    # pre-formatted body. send_email_sms expects signal
                    # objects, so we call its primitives directly here.
                    digits = "".join(c for c in config.sms_to if c.isdigit())
                    if len(digits) == 11 and digits.startswith("1"):
                        digits = digits[1:]
                    if len(digits) == 10:
                        gateway = CARRIER_GATEWAYS.get(config.sms_carrier)
                        from config.settings import settings as _settings
                        if gateway and _settings.smtp_email and _settings.smtp_password:
                            msg = MIMEText(body)
                            msg["From"] = _settings.smtp_email
                            msg["To"] = f"{digits}@{gateway}"
                            msg["Subject"] = ""
                            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=_SMTP_TIMEOUT) as server:
                                server.login(_settings.smtp_email, _settings.smtp_password)
                                server.send_message(msg)
                            _record_sms_fingerprint(fp)
                            results["sms"] = True
                            logger.info("Intraday email SMS sent (%d chars)", len(body))
                elif config.sms_method == "twilio":
                    from config.settings import settings as _settings
                    if _settings.twilio_account_sid and _settings.twilio_auth_token and _settings.twilio_from_number:
                        from twilio.rest import Client
                        client = Client(_settings.twilio_account_sid, _settings.twilio_auth_token)
                        client.messages.create(
                            body=body,
                            from_=_settings.twilio_from_number,
                            to=config.sms_to,
                        )
                        _record_sms_fingerprint(fp)
                        results["sms"] = True
                        logger.info("Intraday Twilio SMS sent (%d chars)", len(body))
            except Exception as e:
                logger.warning("Intraday SMS dispatch failed: %s", e)

    try:
        from src.data.redis_store import get_push_tokens
        tokens = list(get_push_tokens().keys())
        if tokens:
            results["push"] = send_expo_push_intraday(tokens, patterns)
    except Exception as e:
        logger.debug("Intraday push dispatch failed: %s", e)

    return results


def _format_watch_body(watches: list, max_chars: int = 155) -> str:
    """Short SMS / push body for forming-setup watches. Carrier gateways cap
    at 160 chars, so lines are added only while they fit. Telegram passes a
    larger `max_chars`."""
    lines = [("MSE Watch" if len(watches) == 1 else f"MSE Watch: {len(watches)}")
             + _header_suffix.get()]
    for w in watches:
        if w.watch_type == "box_forming":
            line = f"{w.symbol} box {w.lower:.2f}-{w.upper:.2f}, watch break"
        elif w.watch_type == "vwap_tag":
            line = f"{w.symbol} at VWAP {w.upper:.2f}, watch hold/reject"
        else:
            line = f"{w.symbol} {w.watch_type}"
        if len("\n".join(lines + [line])) > max_chars:
            break
        lines.append(line)
    return "\n".join(lines)


def _send_text_sms(config, body: str) -> bool:
    """Send a pre-formatted SMS body through the configured method."""
    from config.settings import settings as _settings

    if config.sms_method == "email_gateway" and config.sms_carrier:
        digits = "".join(c for c in config.sms_to if c.isdigit())
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        gateway = CARRIER_GATEWAYS.get(config.sms_carrier)
        if len(digits) != 10 or not gateway:
            return False
        if not _settings.smtp_email or not _settings.smtp_password:
            return False
        msg = MIMEText(body)
        msg["From"] = _settings.smtp_email
        msg["To"] = f"{digits}@{gateway}"
        msg["Subject"] = ""
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=_SMTP_TIMEOUT) as server:
            server.login(_settings.smtp_email, _settings.smtp_password)
            server.send_message(msg)
        return True
    if config.sms_method == "twilio":
        if not (
            _settings.twilio_account_sid
            and _settings.twilio_auth_token
            and _settings.twilio_from_number
        ):
            return False
        from twilio.rest import Client
        client = Client(_settings.twilio_account_sid, _settings.twilio_auth_token)
        client.messages.create(
            body=body, from_=_settings.twilio_from_number, to=config.sms_to
        )
        return True
    return False


def dispatch_intraday_watches(watches: list) -> dict:
    """Route forming-setup watches (box forming, VWAP tag) to SMS + push.

    Same gating as the other intraday alerts: auto-alerts must be enabled,
    SMS needs consent, and the 30-minute body fingerprint guards against
    repeats. Callers dedupe per (symbol, watch_type, trading day).
    """
    results = {"sms": False, "push": False, "telegram": False}
    if not watches:
        return results

    config = load_config()
    if not config.auto_alerts_enabled:
        logger.info("Intraday auto-alerts disabled, skipping watch dispatch")
        return results

    results["telegram"] = _send_telegram("watch", _format_watch_body(watches, max_chars=3500))

    body = _format_watch_body(watches)

    if config.sms_to and config.sms_consent:
        fp = _fingerprint_of_body(f"watch_sms:{body}")
        recent = _recent_sms_fingerprints()
        if fp in recent:
            logger.info("Watch SMS suppressed (duplicate body sent %s)", recent[fp])
        else:
            try:
                if _send_text_sms(config, body):
                    _record_sms_fingerprint(fp)
                    results["sms"] = True
                    logger.info("Watch SMS sent (%d chars)", len(body))
            except Exception as e:
                logger.warning("Watch SMS dispatch failed: %s", e)

    try:
        from src.data.redis_store import get_push_tokens
        tokens = list(get_push_tokens().keys())
        if tokens:
            fp = _fingerprint_of_body(f"watch_push:{body}")
            if fp in _recent_sms_fingerprints():
                logger.info("Watch push suppressed (duplicate body)")
            else:
                messages = [
                    {
                        "to": t,
                        "sound": "default",
                        "title": "MSE Setup Forming",
                        "body": body,
                        "data": {
                            "type": "intraday_watch",
                            "url": f"mse://instrument/{watches[0].symbol}",
                        },
                    }
                    for t in tokens
                ]
                resp = http_requests.post(
                    _EXPO_PUSH_URL,
                    json=messages,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    timeout=10,
                )
                if 200 <= resp.status_code < 300:
                    _record_sms_fingerprint(fp)
                    results["push"] = True
                else:
                    logger.warning("Watch push failed: HTTP %d", resp.status_code)
    except Exception as e:
        logger.debug("Watch push dispatch failed: %s", e)

    return results


def send_expo_push(tokens: list[str], signals: list) -> bool:
    """Send a push notification to each Expo push token via the Expo push API.

    No Apple/Google credentials required — Expo's service brokers to APNs
    and FCM on our behalf. Returns True if ANY token was delivered to
    the Expo service (individual delivery statuses are async and logged).
    """
    if not tokens or not signals:
        return False

    deduped = _deduped_signals_for_sms(signals)
    deduped.sort(key=lambda s: getattr(s, "confidence", 0), reverse=True)
    top = deduped[:5]
    title = "MSE Signal Alert" if len(deduped) == 1 else f"MSE: {len(deduped)} new signals"
    body_lines = []
    for s in top:
        arrow = "+" if s.action.value == "BUY" else "-"
        body_lines.append(
            f"{arrow}{s.symbol} {s.action.value} ${s.entry:.2f}"
            f" ({s.confidence*100:.0f}%)"
        )
    body = "\n".join(body_lines)

    # Fingerprint suppression — same 30-min window as SMS.
    fp = _fingerprint_of_body(f"push:{body}")
    recent = _recent_sms_fingerprints()
    if fp in recent:
        logger.info("Expo push suppressed (duplicate body sent %s)", recent[fp])
        return False

    # Expo accepts a batched payload up to 100 messages.
    messages = [
        {
            "to": t,
            "sound": "default",
            "title": title,
            "body": body,
            "data": {
                "type": "signal_alert",
                # Deep link into the instrument page of the top-scoring signal
                "url": f"mse://instrument/{deduped[0].symbol}" if deduped else "",
            },
        }
        for t in tokens
    ]

    try:
        resp = http_requests.post(
            _EXPO_PUSH_URL,
            json=messages,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=10,
        )
        ok = 200 <= resp.status_code < 300
        if ok:
            _record_sms_fingerprint(fp)
            logger.info("Expo push sent to %d tokens (%d chars)", len(tokens), len(body))
        else:
            logger.warning("Expo push failed: HTTP %d: %s", resp.status_code, resp.text[:200])
        return ok
    except Exception as e:
        logger.warning("Expo push error: %s", e)
        return False

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
    lines = ["MSE Alert" + _header_suffix.get()]
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

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=_SMTP_TIMEOUT) as server:
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
    results = {"webhook": False, "sms": False, "push": False, "telegram": False}

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

    # Telegram first: it is the quick channel, and a slow SMS attempt must not delay it.
    results["telegram"] = _send_telegram("signals", _format_telegram_signals(filtered))

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

    # Mobile push notifications (Expo). Any tokens registered from the
    # mobile app get a silent-friendly push instead of (or in addition
    # to) SMS.
    try:
        from src.data.redis_store import get_push_tokens
        tokens = list(get_push_tokens().keys())
        if tokens:
            results["push"] = send_expo_push(tokens, filtered)
        else:
            logger.info("Push skipped: no Expo tokens registered")
    except Exception as e:
        logger.debug("Expo push dispatch failed: %s", e)

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
                "telegram_sent": results["telegram"],
            })
    except Exception as e:
        logger.debug("Alert history logging failed: %s", e)

    return results
