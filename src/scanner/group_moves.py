"""Peer groups moving together early in the session. Scorecard only: these
are measured, never alerted, until the scorecard shows they are worth it.

Why: CLSK closed 10% up or down on 14 of 221 sessions in 2026, and on 13 of
them RIOT and MARA moved the same way. Most of each move happened during
the session, not in the opening gap. But an early move alone did not pay:
a 6% CLSK move by 10:30 caught 13 of the 14 days yet fired on 43, and the
rest of the day averaged -0.25% in the move's direction. This records, at
one fixed checkpoint each day, which group members were moving together,
so the scorecard can show over weeks whether such mornings continue.

The rule: when the session data (15 minutes delayed on the free plan) first
reaches 10:30 New York time, a group "moves" when at least MIN_MEMBERS of
its members are MIN_MOVE_PCT or more from the previous close in the same
direction. Every member past the threshold is logged at its latest price.
Days when the server was not running at the checkpoint are skipped rather
than measured from a different time.
"""

from __future__ import annotations

import logging
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src.data import client

logger = logging.getLogger("mse.group_moves")

ET = ZoneInfo("America/New_York")
CHECK_FROM = dtime(10, 30)     # session data must have reached this time
CHECK_UNTIL = dtime(11, 0)     # and not gone past this, so every record uses the same checkpoint
MIN_MOVE_PCT = 3.0
MIN_MEMBERS = 3
BAR_MINUTES = 5


def groups() -> dict[str, list[str]]:
    from src.scanner.spike_reversal import EXTRA_GROUPS
    return {"crypto_miners": list(EXTRA_GROUPS["crypto_miners"])}


def detect(intraday: dict[str, pd.DataFrame], prev_close: dict[str, float],
           now: datetime | None = None, group_map: dict[str, list[str]] | None = None) -> list[dict]:
    """Scorecard alerts for groups moving together at the 10:30 checkpoint.
    Pure: takes 5-minute bars and previous closes, returns
    [{symbol, kind, direction, price, group, move_pct}]."""
    from src.scanner.intraday_movers import session_bars
    out: list[dict] = []
    for group, members in (group_map or groups()).items():
        moves: dict[str, tuple[float, float]] = {}
        for sym in members:
            prev = prev_close.get(sym)
            bars = session_bars(intraday.get(sym), now=now)
            if not prev or prev <= 0 or bars.empty:
                continue
            reached = (bars.index[-1] + timedelta(minutes=BAR_MINUTES)).time()
            if not (CHECK_FROM <= reached < CHECK_UNTIL):
                continue
            price = float(bars["close"].iloc[-1])
            moves[sym] = ((price / prev - 1) * 100, price)
        for direction, sign in (("up", 1), ("down", -1)):
            hits = {s: v for s, v in moves.items() if v[0] * sign >= MIN_MOVE_PCT}
            if len(hits) >= MIN_MEMBERS:
                for sym, (chg, price) in sorted(hits.items(), key=lambda kv: -abs(kv[1][0])):
                    out.append({"symbol": sym, "kind": f"{group}_move", "direction": direction,
                                "price": round(price, 4), "group": group, "move_pct": round(chg, 2)})
    return out


def scan(now: datetime | None = None) -> list[dict]:
    """Fetch the members' bars and run detect(). Outside the checkpoint it
    returns [] without fetching anything. Never raises."""
    now_et = (now or datetime.now(tz=ET)).astimezone(ET)
    # With 15-minute-delayed data the checkpoint arrives at about 10:45;
    # outside 10:30-11:30 there is nothing to look for.
    if not (dtime(10, 30) <= now_et.time() < dtime(11, 30)) or now_et.weekday() >= 5:
        return []
    try:
        gmap = groups()
        members = sorted({s for m in gmap.values() for s in m})
        intraday = client.get_intraday_multi_bars(members, minutes_back=180, timeframe_minutes=BAR_MINUTES)
        daily = client.get_multi_bars(members, days=10)
        today = now_et.date()
        prev_close: dict[str, float] = {}
        for sym, df in daily.items():
            if df is None or df.empty:
                continue
            idx = pd.to_datetime(df.index)
            idx = idx.tz_convert(ET) if idx.tz is not None else idx.tz_localize("UTC").tz_convert(ET)
            before = df[[d < today for d in idx.date]]
            if not before.empty:
                prev_close[sym] = float(before["close"].iloc[-1])
        return detect(intraday, prev_close, now=now_et, group_map=gmap)
    except Exception as e:
        logger.warning("Group move check failed: %s", str(e)[:160])
        return []
