"""Rules every alert passes before it is sent, whichever scanner raised it.

1. Market hours. Alerts go out only while the market is open (09:30-16:00
   New York time on trading days). On 2026-11-11 and 11-12 daily signals
   arrived at 16:04 and 16:12, after the close, when nothing could be done.
2. No contradictions. An alert is held back when an alert in the opposite
   direction on the same stock went out within the last hour, from any
   scanner: pattern alerts, intraday movers setups and daily signals. On
   2026-11-12 AMD got pattern SELLs at 10:33 and 12:43, then a movers BUY at
   13:11 and a daily-signal BUY at 15:46.

The record of what went out is shared by both scan loops and kept in Redis,
so a restart does not forget it. Direction-neutral alerts (setup watches)
are not affected.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger("mse.alert_rules")

ET = ZoneInfo("America/New_York")
OPEN, CLOSE = dtime(9, 30), dtime(16, 0)
WINDOW_SECONDS = 60 * 60
RECENT_KEY = "mse:recent_alert_directions"

_lock = threading.Lock()
_recent: dict[str, list[list]] = {}      # symbol -> [[direction, epoch seconds], ...]
_loaded = False
_trading_days: dict[str, bool] = {}


def _redis():
    try:
        from src.data.redis_store import _get_redis
        return _get_redis()
    except Exception:
        return None


# ------------------------------------------------------------ market hours

def trading_day(day) -> bool:
    """Alpaca's calendar, asked once per date. Unreadable counts as open."""
    key = day.isoformat()
    if key not in _trading_days:
        from src.notifications.heartbeat import _trading_day
        _trading_days[key] = _trading_day(day)
    return _trading_days[key]


def market_open(now: datetime | None = None) -> bool:
    """True from 09:30 to 16:00 New York time on trading days."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    et = now.astimezone(ET)
    if et.weekday() >= 5 or not (OPEN <= et.time() < CLOSE):
        return False
    return trading_day(et.date())


# ---------------------------------------------------------- contradictions

def direction_of(item) -> str | None:
    """"up", "down", or None for alerts with no direction. Understands
    intraday patterns (pattern_type) and signals (action BUY or SELL)."""
    pattern_type = getattr(item, "pattern_type", None)
    if pattern_type:
        return "down" if pattern_type in ("inverted_v", "breakdown") else "up"
    action = getattr(item, "action", None)
    action = str(getattr(action, "value", action) or "").upper()
    if action == "BUY":
        return "up"
    if action == "SELL":
        return "down"
    return None


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    r = _redis()
    if not r:
        return
    try:
        raw = r.get(RECENT_KEY)
        data = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
        if isinstance(data, dict):
            for sym, marks in data.items():
                good = [[str(m[0]), float(m[1])] for m in marks
                        if isinstance(m, (list, tuple)) and len(m) == 2 and m[0] in ("up", "down")]
                if good:
                    _recent[str(sym)] = good
    except Exception as e:
        logger.debug("Recent alert directions unreadable: %s", e)


def _prune(now_ts: float, window: float) -> None:
    for sym in list(_recent):
        kept = [m for m in _recent[sym] if 0 <= now_ts - m[1] < window]
        if kept:
            _recent[sym] = kept
        else:
            del _recent[sym]


def _save() -> None:
    r = _redis()
    if not r:
        return
    try:
        r.set(RECENT_KEY, json.dumps(_recent))
    except Exception as e:
        logger.debug("Recent alert directions not saved: %s", e)


def claim(items: list, now_ts: float | None = None,
          window: float = WINDOW_SECONDS) -> tuple[list, list]:
    """(to send, held back). An item is held back when an alert in the
    opposite direction on the same stock went out within `window` seconds,
    or when this batch holds both directions for that stock. Items to send
    are recorded at once, under the same lock, so two loops cannot both
    send opposite alerts at the same moment. Never raises."""
    now_ts = time.time() if now_ts is None else now_ts
    try:
        with _lock:
            _load()
            _prune(now_ts, window)
            batch: dict[str, set[str]] = {}
            for it in items:
                d = direction_of(it)
                if d:
                    batch.setdefault(it.symbol, set()).add(d)
            send, held = [], []
            for it in items:
                d = direction_of(it)
                if d is None:
                    send.append(it)
                    continue
                opposite = "down" if d == "up" else "up"
                recent = {m[0] for m in _recent.get(it.symbol, [])}
                if opposite in recent or opposite in batch[it.symbol]:
                    held.append(it)
                else:
                    send.append(it)
            for it in send:
                d = direction_of(it)
                if d:
                    _recent.setdefault(it.symbol, []).append([d, now_ts])
            if send:
                _save()
        return send, held
    except Exception as e:
        logger.warning("Alert conflict check failed, sending as is: %s", e)
        return list(items), []


def describe(held: list) -> str:
    return ", ".join(
        f"{it.symbol} {getattr(it, 'pattern_type', None) or getattr(getattr(it, 'action', None), 'value', '')}"
        for it in held)
