"""Telegram alerts through a bot, over plain HTTPS.

Why this exists: the free hosting plan blocks outbound email ports, so the
email-to-text route fails there, and carrier email gateways are being
retired. A Telegram bot needs only an HTTPS request.

The bot token and chat id come from the environment (TELEGRAM_BOT_TOKEN,
TELEGRAM_CHAT_ID), never from the saved notification config: that config
is readable through a public endpoint. The token is also part of the
request URL, and HTTP errors quote the URL, so every error string is
redacted before it is logged or returned.
"""

import logging
import re
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from config.settings import settings

logger = logging.getLogger("mse.telegram")
# The bot token is part of the request path, and urllib3 logs request paths
# at DEBUG. Keep that logger above DEBUG even if the app's level is lowered.
logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

_API = "https://api.telegram.org"
MAX_CHARS = 4000            # Telegram refuses messages over 4096 characters
_TIMEOUT = 10
_ATTEMPTS = 2               # one retry on a network error, 5xx or rate limit
_MAX_RETRY_WAIT = 5.0
_TOKEN_SHAPE = re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}")
_ET = ZoneInfo("America/New_York")

_lock = threading.Lock()
_state: dict = {"sent": 0, "failed": 0, "last_ok_at": None,
                "last_attempt_at": None, "last_error": None}

_HINTS = {
    401: "the bot token was rejected; check TELEGRAM_BOT_TOKEN",
    403: "the bot may not message this chat; open the bot in Telegram and press Start",
    404: "the bot token was rejected; check TELEGRAM_BOT_TOKEN",
}


def _creds() -> tuple[str, str]:
    return ((settings.telegram_bot_token or "").strip(),
            (settings.telegram_chat_id or "").strip())


def configured() -> bool:
    token, chat = _creds()
    return bool(token and chat)


def redact(text: str) -> str:
    """Remove the bot token, and anything shaped like one, from a string."""
    text = str(text)
    token, _ = _creds()
    if token:
        text = text.replace(token, "[token]")
    return _TOKEN_SHAPE.sub("[token]", text)


def _fit(body: str) -> str:
    if len(body) <= MAX_CHARS:
        return body
    cut = body[:MAX_CHARS]
    if "\n" in cut:
        cut = cut[:cut.rfind("\n")]
    return cut + "\n(more not shown)"


def _record(error: str | None) -> None:
    now = time.time()
    with _lock:
        _state["last_attempt_at"] = now
        _state["last_error"] = error
        if error is None:
            _state["sent"] += 1
            _state["last_ok_at"] = now
        else:
            _state["failed"] += 1


def send_text(body: str) -> bool:
    """Send one plain-text message to the configured chat. Never raises.
    Plain text on purpose: tickers and setup names contain characters that
    Telegram's Markdown mode rejects."""
    token, chat = _creds()
    if not token or not chat or not (body or "").strip():
        return False
    payload = {"chat_id": chat, "text": _fit(body), "disable_web_page_preview": True}
    error = "not attempted"
    for attempt in range(_ATTEMPTS):
        wait = 2.0
        try:
            resp = requests.post(f"{_API}/bot{token}/sendMessage", json=payload, timeout=_TIMEOUT)
            if resp.status_code == 200:
                _record(None)
                logger.info("Telegram alert sent (%d chars)", len(payload["text"]))
                return True
            detail, retry_after = "", None
            try:
                data = resp.json()
                detail = str(data.get("description") or "")
                retry_after = (data.get("parameters") or {}).get("retry_after")
            except Exception:
                pass
            error = f"HTTP {resp.status_code}" + (f": {detail}" if detail else "")
            if resp.status_code == 400 and "chat not found" in detail.lower():
                error += " (check TELEGRAM_CHAT_ID, and press Start in the bot's chat)"
            elif resp.status_code in _HINTS:
                error += f" ({_HINTS[resp.status_code]})"
            retryable = resp.status_code == 429 or resp.status_code >= 500
            if not retryable:
                break
            if isinstance(retry_after, (int, float)) and retry_after > 0:
                if retry_after > _MAX_RETRY_WAIT:
                    break                       # told to wait too long; give up now
                wait = float(retry_after)
        except Exception as e:                  # network error, timeout
            error = f"{type(e).__name__}: {e}"
        if attempt + 1 < _ATTEMPTS:
            time.sleep(wait)
    error = redact(error)[:300]
    _record(error)
    logger.warning("Telegram alert failed: %s", error)
    return False


def status() -> dict:
    """Whether Telegram is set up and how the last send went. No secrets:
    neither the token nor the chat id is returned."""
    token, chat = _creds()
    with _lock:
        snap = dict(_state)

    def iso(ts):
        return datetime.fromtimestamp(ts, tz=_ET).isoformat(timespec="seconds") if ts else None

    return {
        "configured": bool(token and chat),
        "has_token": bool(token),
        "has_chat_id": bool(chat),
        "sent": snap["sent"],
        "failed": snap["failed"],
        "last_ok_at": iso(snap["last_ok_at"]),
        "last_attempt_at": iso(snap["last_attempt_at"]),
        "last_error": snap["last_error"],
    }
