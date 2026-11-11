"""Keep a sleeping host awake through the trading day.

Render's free plan stops a web service after about 15 minutes without an
inbound request, and a stopped service runs none of the background loops
(intraday alerts, scorecard, auto-trader, end-of-day close). This loop asks
for the service's own public address every few minutes on weekdays inside a
New York time window, which counts as traffic.

It can only keep an awake service awake. Nothing here runs while the
service is asleep, so something outside has to wake it first: see
`.github/workflows/wake.yml`.
"""

import logging
import os
import threading
import time
from datetime import datetime, time as dtime, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests

from config.settings import settings

logger = logging.getLogger("mse.keepalive")

ET = ZoneInfo("America/New_York")
DEFAULT_START = dtime(4, 0)
DEFAULT_END = dtime(16, 15)
MIN_INTERVAL = 60
MAX_INTERVAL = 780          # the host sleeps at 15 minutes; stay under it
RETRY_AFTER = 60            # a failed request is retried sooner
STARTUP_DELAY = 45          # the server is not listening yet when the loop starts
_TIMEOUT = 20

_lock = threading.Lock()
_state: dict = {"pings": 0, "failures": 0, "last_ok_at": None,
                "last_attempt_at": None, "last_error": None}


def _parse_hhmm(value: str, default: dtime, what: str) -> dtime:
    try:
        hh, mm = str(value).strip().split(":")
        return dtime(int(hh), int(mm))
    except (ValueError, TypeError):
        logger.warning("Keep-alive %s time %r is not HH:MM; using %s",
                       what, value, default.strftime("%H:%M"))
        return default


def window() -> tuple[dtime, dtime]:
    """Start and end of the daily window in New York time. A window that
    does not end after it starts is a mistake, so the defaults are used."""
    start = _parse_hhmm(settings.keep_alive_start_et, DEFAULT_START, "start")
    end = _parse_hhmm(settings.keep_alive_end_et, DEFAULT_END, "end")
    if end <= start:
        logger.warning("Keep-alive window %s to %s is empty; using the defaults",
                       start.strftime("%H:%M"), end.strftime("%H:%M"))
        return DEFAULT_START, DEFAULT_END
    return start, end


def interval() -> int:
    try:
        seconds = int(settings.keep_alive_interval_seconds)
    except (ValueError, TypeError):
        seconds = 300
    return max(MIN_INTERVAL, min(MAX_INTERVAL, seconds))


def target_url() -> str:
    """Address to request, or "" when there is none (local runs).
    KEEP_ALIVE_URL wins; otherwise the address Render gives the service."""
    base = (settings.keep_alive_url or os.environ.get("RENDER_EXTERNAL_URL") or "").strip()
    if not base:
        return ""
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        logger.warning("Keep-alive address %r is not an http(s) URL; keep-alive is off", base)
        return ""
    return f"{parts.scheme}://{parts.netloc}/health"


def in_window(now: datetime | None = None) -> bool:
    """True on weekdays between the start and end times, New York time.
    Market holidays are not excluded: staying awake on one costs hours,
    while sleeping through a session costs the whole day's alerts."""
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    et = now.astimezone(ET)
    if et.weekday() >= 5:
        return False
    start, end = window()
    return start <= et.time().replace(second=0, microsecond=0) <= end


def ping(url: str) -> bool:
    """One request to our own address. Never raises."""
    error = None
    try:
        resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "mse-keepalive"})
        if resp.status_code >= 400:
            error = f"HTTP {resp.status_code}"
    except Exception as e:  # network errors, timeouts, bad URL
        error = f"{type(e).__name__}: {e}"[:200]
    now = time.time()
    with _lock:
        was_failing = _state["last_error"] is not None
        _state["last_attempt_at"] = now
        _state["last_error"] = error
        if error is None:
            _state["pings"] += 1
            _state["last_ok_at"] = now
        else:
            _state["failures"] += 1
    if error is not None:
        logger.warning("Keep-alive request failed: %s", error)
    elif was_failing:
        logger.info("Keep-alive request succeeded again")
    return error is None


def status() -> dict:
    """What the loop is doing, for /health/keepalive. No secrets."""
    start, end = window()
    url = target_url()
    with _lock:
        snap = dict(_state)

    def iso(ts):
        return datetime.fromtimestamp(ts, tz=ET).isoformat(timespec="seconds") if ts else None

    return {
        "enabled": bool(settings.keep_alive_enabled),
        "active": bool(settings.keep_alive_enabled) and bool(url),
        "url": url or None,
        "window_et": f"{start.strftime('%H:%M')} to {end.strftime('%H:%M')} weekdays",
        "interval_seconds": interval(),
        "in_window_now": in_window(),
        "pings": snap["pings"],
        "failures": snap["failures"],
        "last_ok_at": iso(snap["last_ok_at"]),
        "last_attempt_at": iso(snap["last_attempt_at"]),
        "last_error": snap["last_error"],
    }


def run(stop: threading.Event) -> None:
    """Background loop. Returns at once when switched off or when there is
    no address to request, so local runs do nothing."""
    if not settings.keep_alive_enabled:
        logger.info("Keep-alive is switched off (KEEP_ALIVE_ENABLED)")
        return
    url = target_url()
    if not url:
        logger.info("Keep-alive off: no public address (set KEEP_ALIVE_URL, "
                    "or run on Render which provides RENDER_EXTERNAL_URL)")
        return
    start, end = window()
    logger.info("Keep-alive on: %s every %ss, %s to %s New York time on weekdays",
                url, interval(), start.strftime("%H:%M"), end.strftime("%H:%M"))
    # A request sent before the server accepts connections fails and logs a
    # warning on every start; a fresh start is awake for 15 minutes anyway.
    if STARTUP_DELAY > 0:
        stop.wait(STARTUP_DELAY)
    was_in = None
    while not stop.is_set():
        wait = interval()
        try:
            now_in = in_window()
            if now_in != was_in:
                logger.info("Keep-alive window %s", "open" if now_in else
                            "closed; the service may sleep until the next request")
                was_in = now_in
            if now_in and not ping(url):
                wait = min(RETRY_AFTER, wait)
        except Exception as e:  # the loop must outlive any single bad cycle
            logger.warning("Keep-alive cycle failed: %s", e)
        stop.wait(wait)
