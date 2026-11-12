"""Telegram status messages: a morning check before the open, and a notice
when the server restarts while it is supposed to be awake.

Why: on 2026-11-11 the server was killed for running out of memory about a
dozen times and was down for the last two hours of the session, and nothing
said so. These messages make a dead or restarting server visible.

Both need Telegram set up (src/notifications/telegram.py). The server's
"last seen alive" time and today's restart count are kept in Redis, so a
restart can tell a deploy from a crash from a wake after sleeping.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

from config.settings import settings

logger = logging.getLogger("mse.heartbeat")

ET = ZoneInfo("America/New_York")
ALIVE_KEY = "mse:alive"              # epoch seconds this server was last known running
BOOT_KEY = "mse:boot"                # {"commit", "date", "restarts", "last_notice"}
HEARTBEAT_KEY = "mse:heartbeat_date"
ALIVE_EVERY = 120                    # seconds between "alive" writes
NOTICE_GAP = 30 * 60                 # at most one restart notice per half hour (crash loops)
SLEEP_GAP = 20 * 60                  # silent this long before the restart: it was down, not a quick crash
BOOT_DELAY = 20                      # seconds after startup before the restart check
RETRY_AFTER = 300                    # a failed morning check is retried after this long
LAST_CALL = dtime(16, 0)             # no morning check after the close

_started_at = time.time()
_boot_checked = threading.Event()    # "alive" is not written until the previous value has been read
_lock = threading.Lock()
_state = {"last_alive_write": 0.0, "heartbeat_date": "", "next_try": 0.0, "restarts_today": None}


def _redis():
    try:
        from src.data.redis_store import _get_redis
        return _get_redis()
    except Exception:
        return None


def _et(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ET)


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=ET).strftime("%-I:%M %p").lower().replace(" ", "")


def _telegram_ready() -> bool:
    try:
        from src.notifications import telegram
        return telegram.configured()
    except Exception:
        return False


def _send(text: str) -> bool:
    try:
        from src.notifications import telegram
        return telegram.send_text(text)
    except Exception as e:
        logger.warning("Status message not sent: %s", type(e).__name__)
        return False


# ------------------------------------------------------------------ alive

def mark_alive(now_ts: float | None = None) -> bool:
    """Record that the server is running, at most every ALIVE_EVERY seconds.
    Does nothing until the restart check has read the previous value."""
    if not _boot_checked.is_set():
        return False
    now_ts = time.time() if now_ts is None else now_ts
    with _lock:
        if now_ts - _state["last_alive_write"] < ALIVE_EVERY:
            return False
        _state["last_alive_write"] = now_ts
    r = _redis()
    if not r:
        return False
    try:
        r.set(ALIVE_KEY, str(int(now_ts)))
        return True
    except Exception as e:
        logger.debug("Alive mark not saved: %s", e)
        return False


# ---------------------------------------------------------- restart notice

_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return str(n) + _SUFFIX.get(n % 10, "th")


def restart_notice(now: datetime | None = None) -> str | None:
    """Run once at startup. Counts today's starts, works out why the server
    restarted, and sends a Telegram notice when the restart happened while the
    server should be awake. Returns the text sent, or None. Never raises."""
    try:
        from src import keepalive
        et = _et(now)
        now_ts = et.timestamp()
        today = et.date().isoformat()
        r = _redis()
        prev_alive, boot = 0.0, {}
        if r:
            try:
                prev_alive = float(r.get(ALIVE_KEY) or 0)
                raw = r.get(BOOT_KEY)
                boot = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
                if not isinstance(boot, dict):
                    boot = {}
            except Exception as e:
                logger.debug("Restart history unreadable: %s", e)
                prev_alive, boot = 0.0, {}
        commit = (os.environ.get("RENDER_GIT_COMMIT") or "")[:7]
        restarts = (int(boot.get("restarts") or 0) if boot.get("date") == today else 0) + 1
        with _lock:
            _state["restarts_today"] = restarts

        if commit and boot.get("commit") and commit != boot.get("commit"):
            reason = f"after a deploy (commit {commit})"
        elif prev_alive and now_ts - prev_alive > SLEEP_GAP:
            reason = f"after being down since {_hhmm(prev_alive)} ET (asleep or crashed)"
        elif prev_alive:
            reason = ("unexpectedly, probably out of memory "
                      "(Render's Events tab will say)")
        else:
            reason = ""

        last_notice = float(boot.get("last_notice") or 0)
        should = (settings.restart_notice_enabled and _telegram_ready()
                  and keepalive.in_window(et) and now_ts - last_notice >= NOTICE_GAP)
        sent = None
        if should:
            text = (f"MSE server restarted at {_hhmm(now_ts)} ET"
                    + (f" {reason}" if reason else "")
                    + f". {_ordinal(restarts)} start today. Alerts resume within about 5 minutes.")
            if _send(text):
                sent, last_notice = text, now_ts
        if r:
            try:
                r.set(BOOT_KEY, json.dumps({"commit": commit or boot.get("commit", ""),
                                            "date": today, "restarts": restarts,
                                            "last_notice": last_notice}))
            except Exception as e:
                logger.debug("Restart history not saved: %s", e)
        logger.info("Startup recorded: %s start today%s%s", _ordinal(restarts),
                    f", {reason}" if reason else "", ", notice sent" if sent else "")
        return sent
    except Exception as e:
        logger.warning("Restart check failed: %s", e)
        return None
    finally:
        _boot_checked.set()


TICK = 30   # seconds between morning-check and alive ticks


def run(stop: threading.Event) -> None:
    """Background thread started from the app's lifespan: after the server
    settles, run the restart check once, then tick every TICK seconds. Kept
    apart from the auto-trader's close loop so a slow Telegram send can
    never delay the end-of-day close."""
    if stop.wait(BOOT_DELAY):
        _boot_checked.set()
        return
    restart_notice()
    while not stop.is_set():
        heartbeat_tick()
        stop.wait(TICK)


# ---------------------------------------------------------- morning check

def _trading_day(day) -> bool:
    """True unless Alpaca's calendar says the market is closed that day.
    An unreadable calendar counts as open: a stray message on a holiday is
    better than a missing one on a trading day."""
    try:
        from alpaca.trading.requests import GetCalendarRequest
        from src.data.client import _get_trading_client
        days = _get_trading_client().get_calendar(GetCalendarRequest(start=day, end=day))
        return bool(days)
    except Exception as e:
        logger.debug("Market calendar unreadable: %s", e)
        return True


def _part(fn, default="unknown"):
    try:
        return fn()
    except Exception:
        return default


def morning_text(et: datetime, late: bool) -> str:
    """The morning check's message. Each line degrades to "unknown" on its own."""
    from src import heavy

    def memory():
        now, peak = heavy.rss_mb(), heavy.peak_mb()
        used = f"{now:.0f}" if now is not None else "?"
        line = f"memory {used} of {heavy.LIMIT_MB} MB (peak {peak:.0f})"
        skipped = heavy.status().get("skipped") or {}
        if skipped:
            line += f"; skipped for memory: {', '.join(sorted(skipped))}"
        return line

    def prices():
        from src.data import freshness
        d = freshness.data_delay()
        if not d.get("session_active"):
            return "delay is measured once the session opens (usually about 15 min on the free plan)"
        return f"about {d['delay_minutes']} min behind" if d.get("delayed") else "current"

    def trader():
        from src.trading import auto_trader
        s = auto_trader.status()
        paper = "paper" if s.get("paper") else "NOT paper"
        return f"{s.get('mode')} ({paper}), {len(s.get('trades') or [])} trades so far"

    def alerts():
        from src.notifications.dispatcher import load_config
        c = load_config()
        return (f"on, minimum confidence {c.min_confidence * 100:.0f}%"
                if c.auto_alerts_enabled else "OFF (Notifications page)")

    restarts = _state.get("restarts_today")
    head = f"MSE morning check, {et.strftime('%a %b %-d')} {_hhmm(et.timestamp())} ET"
    if late:
        head += " (late: the server was not running earlier)"
    lines = [
        head,
        f"Server: up since {_hhmm(_started_at)} ET, {_part(memory)}",
        f"Starts today: {restarts if restarts is not None else 'unknown'}",
        f"Prices: {_part(prices)}",
        f"Auto-trader: {_part(trader)}",
        f"Alerts: {_part(alerts)}",
    ]
    return "\n".join(lines)


def heartbeat_tick(now: datetime | None = None) -> str | None:
    """Called every 30 s from the guard loop. Marks the server alive and sends
    the morning check once per trading day, from settings.heartbeat_et until
    the close. Returns the text sent, or None. Never raises."""
    try:
        mark_alive()
        if not settings.heartbeat_enabled or not _telegram_ready():
            return None
        from src import keepalive
        et = _et(now)
        if et.weekday() >= 5:
            return None
        start = keepalive._parse_hhmm(settings.heartbeat_et, dtime(9, 25), "heartbeat")
        if not (start <= et.time() < LAST_CALL):
            return None
        today = et.date().isoformat()
        with _lock:
            if _state["heartbeat_date"] == today or time.time() < _state["next_try"]:
                return None
        r = _redis()
        if r:
            try:
                if r.get(HEARTBEAT_KEY) == today:
                    with _lock:
                        _state["heartbeat_date"] = today
                    return None
            except Exception:
                pass
        if not _trading_day(et.date()):
            with _lock:
                _state["heartbeat_date"] = today
            logger.info("Morning check skipped: market closed today")
            return None
        late = et - et.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0) \
            > timedelta(minutes=15)
        text = morning_text(et, late)
        if not _send(text):
            with _lock:
                _state["next_try"] = time.time() + RETRY_AFTER
            return None
        with _lock:
            _state["heartbeat_date"] = today
        if r:
            try:
                r.set(HEARTBEAT_KEY, today)
            except Exception:
                pass
        logger.info("Morning check sent")
        return text
    except Exception as e:
        logger.warning("Morning check failed: %s", e)
        return None
