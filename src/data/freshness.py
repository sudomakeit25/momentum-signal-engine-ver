"""How old is the market data?

Alpaca's free plan delays full-market bars by 15 minutes. Everything
intraday in this app (movers, setups, alerts, spike detection, the paper
auto-trader's signals) reads those bars, so the delay has to be measured
and shown, not assumed away.

The delay is measured, not hard-coded: the newest 1-minute bar of a few
always-active symbols is compared with the clock. If the data plan is ever
upgraded the label disappears by itself.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src.data import client

logger = logging.getLogger("mse.freshness")

ET = ZoneInfo("America/New_York")
_PROBE = ["SPY", "QQQ", "NVDA"]       # trade every minute, pre-market included
_SESSION_START = dtime(4, 0)
_SESSION_END = dtime(20, 0)
_DELAYED_FROM = 5                      # minutes behind before it is called delayed
_TTL = 60
_cache: tuple[float, dict] | None = None


def measure_delay(bars: dict[str, pd.DataFrame], now: datetime) -> int | None:
    """Minutes between now and the end of the newest 1-minute bar across
    the probe symbols. None if there are no bars."""
    newest = None
    for df in bars.values():
        if df is None or df.empty:
            continue
        idx = pd.to_datetime(df.index)
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        last = idx.max()
        newest = last if newest is None or last > newest else newest
    if newest is None:
        return None
    bar_end = newest.to_pydatetime() + timedelta(minutes=1)
    return max(int((now - bar_end).total_seconds() // 60), 0)


def data_delay(now: datetime | None = None) -> dict:
    """{session_active, delay_minutes, delayed, note}. Never raises."""
    global _cache
    if now is None and _cache and time.time() - _cache[0] < _TTL:
        return _cache[1]

    n = (now or datetime.now(tz=ET)).astimezone(ET)
    out = {"session_active": False, "delay_minutes": None, "delayed": False, "note": "",
           "as_of": n.isoformat(timespec="minutes")}
    if n.weekday() < 5 and _SESSION_START <= n.time() < _SESSION_END:
        out["session_active"] = True
        try:
            bars = client.get_intraday_multi_bars(_PROBE, minutes_back=90, timeframe_minutes=1)
            delay = measure_delay(bars, n)
        except Exception as e:
            logger.warning("Freshness check failed: %s", str(e)[:120])
            delay = None
        # A gap of more than an hour is a halt, holiday or outage, not the
        # plan's delay: say nothing rather than print a nonsense number.
        if delay is not None and delay <= 60:
            out["delay_minutes"] = delay
            out["delayed"] = delay >= _DELAYED_FROM
            if out["delayed"]:
                out["note"] = (
                    f"Market data is about {delay} minutes behind (the data plan delays "
                    "full-market prices). Setups, alerts and the auto-trader's signals "
                    f"reflect prices from about {delay} minutes ago."
                )
    if now is None:
        _cache = (time.time(), out)
    return out


def label(now: datetime | None = None) -> str:
    """Short suffix for alert text, such as ' (15m delayed)', or ''."""
    d = data_delay(now)
    return f" ({d['delay_minutes']}m delayed)" if d["delayed"] else ""
