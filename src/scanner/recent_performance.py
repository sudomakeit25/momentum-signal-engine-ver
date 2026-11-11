"""How a stock did over its last N sessions: day by day, against its peers
and the market, with the headlines from its biggest days.

Describes what the price did. It says nothing about what it will do.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger("mse.recent_performance")

ET = ZoneInfo("America/New_York")
MARKET = "SPY"
MIN_SESSIONS, MAX_SESSIONS = 2, 30
MAX_PEERS = 6
_DEFAULT_PEERS = 4
_TYPICAL_LOOKBACK = 60      # sessions before the window used for "a normal day"
_BIG_DAY_MULT = 2.0         # a big day moves at least this many normal days
_MAX_BIG_DAYS = 5
_VOLUME_LOOKBACK = 20
_HISTORY_DAYS = 170         # calendar days: 30 sessions + 60 before them, with room for holidays
_TTL = 5 * 60
_CACHE_MAX = 300            # served by a public endpoint, so the cache must be bounded
_cache: dict[tuple, tuple[float, dict]] = {}


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _clean(df: pd.DataFrame | None) -> pd.DataFrame:
    """Daily bars, one row per session date, oldest first, bad rows dropped.
    Accepts bars in any order and with duplicate dates."""
    if df is None or len(df) == 0 or "close" not in df.columns:
        return pd.DataFrame()
    d = df.copy()
    idx = pd.to_datetime(d.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(ET)
    d.index = [t.date() for t in idx]
    d = d[~pd.isna(d.index)]
    for col in ("open", "high", "low", "close", "volume"):
        if col not in d.columns:
            d[col] = float("nan")
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d[d["close"].notna() & (d["close"] > 0)]
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return d


def summarize(df: pd.DataFrame | None, sessions: int = 10) -> dict | None:
    """Day-by-day table and totals for the last `sessions` sessions.
    None when there are not enough bars to measure even two sessions."""
    d = _clean(df)
    sessions = max(MIN_SESSIONS, min(MAX_SESSIONS, int(sessions)))
    if len(d) < MIN_SESSIONS + 1:
        return None
    used = min(sessions, len(d) - 1)

    change = d["close"].pct_change() * 100
    avg_vol = d["volume"].rolling(_VOLUME_LOOKBACK, min_periods=5).mean().shift(1)
    win = d.iloc[-used:]
    base_close = float(d["close"].iloc[-used - 1])
    base_date = d.index[-used - 1]

    before = change.iloc[:-used].dropna().abs().iloc[-_TYPICAL_LOOKBACK:]
    typical = float(before.median()) if len(before) >= 10 else None

    rows = []
    for day, r in win.iterrows():
        chg = _num(change.loc[day])
        vol, avg = _num(r["volume"]), _num(avg_vol.loc[day])
        rows.append({
            "date": day.isoformat(),
            "open": _round(r["open"]), "high": _round(r["high"]),
            "low": _round(r["low"]), "close": _round(r["close"]),
            "change_pct": _round(chg),
            "volume": int(vol) if vol is not None else None,
            "rvol": round(vol / avg, 2) if vol is not None and avg else None,
            "cum_pct": _round((float(r["close"]) / base_close - 1) * 100),
            "big": False,
        })

    moves = [(r["change_pct"], r["date"]) for r in rows if r["change_pct"] is not None]
    if typical and typical > 0:
        big = sorted((m for m in moves if abs(m[0]) >= _BIG_DAY_MULT * typical),
                     key=lambda m: abs(m[0]), reverse=True)[:_MAX_BIG_DAYS]
        big_dates = {m[1] for m in big}
        for r in rows:
            r["big"] = r["date"] in big_dates

    highs = [(r["high"] if r["high"] is not None else r["close"], r["date"]) for r in rows]
    lows = [(r["low"] if r["low"] is not None else r["close"], r["date"]) for r in rows]
    hi, hi_date = max(highs)
    lo, lo_date = min(lows)
    last_close = rows[-1]["close"]
    best = max(moves) if moves else (None, None)
    worst = min(moves) if moves else (None, None)
    return {
        "sessions": used,
        "sessions_requested": sessions,
        "base_date": base_date.isoformat(),
        "base_close": round(base_close, 2),
        "last_date": rows[-1]["date"],
        "last_close": last_close,
        "change_pct": rows[-1]["cum_pct"],
        "high": hi, "high_date": hi_date,
        "low": lo, "low_date": lo_date,
        "range_pos": round((last_close - lo) / (hi - lo) * 100, 1) if hi > lo else None,
        "up_days": sum(1 for m in moves if m[0] > 0),
        "down_days": sum(1 for m in moves if m[0] < 0),
        "best_day": {"date": best[1], "change_pct": best[0]} if moves else None,
        "worst_day": {"date": worst[1], "change_pct": worst[0]} if moves else None,
        "avg_abs_move": round(sum(abs(m[0]) for m in moves) / len(moves), 2) if moves else None,
        "typical_move": round(typical, 2) if typical is not None else None,
        "rows": rows,
    }


def _round(v, digits: int = 2) -> float | None:
    f = _num(v)
    return round(f, digits) if f is not None else None


def change_between(df: pd.DataFrame | None, base: date, last: date) -> float | None:
    """Percent change from the close on or before `base` to the close on or
    before `last`, so a peer is measured over the same calendar window."""
    d = _clean(df)
    if d.empty or last < base:
        return None
    start = d[d.index <= base]
    end = d[d.index <= last]
    if start.empty or end.empty:
        return None
    # A peer whose data stops well before the window would give a stale figure.
    if (base - start.index[-1]).days > 5 or (last - end.index[-1]).days > 5:
        return None
    return round((float(end["close"].iloc[-1]) / float(start["close"].iloc[-1]) - 1) * 100, 2)


def _plain(symbol: str) -> bool:
    return symbol.isalpha() and symbol.isupper() and 1 <= len(symbol) <= 5


def peers_for(symbol: str, limit: int = _DEFAULT_PEERS) -> tuple[str | None, list[str]]:
    """(group name, peers) from the app's peer groups. Narrow hand-made groups
    win over broad sectors. Empty when the symbol is in no group."""
    from src.scanner import spike_reversal as sr
    try:
        groups = sr.peer_groups()
    except Exception as e:
        logger.warning("Peer groups unavailable: %s", e)
        groups = dict(sr.EXTRA_GROUPS)
    ordered = [(k, v) for k, v in groups.items() if k in sr.EXTRA_GROUPS] + \
              [(k, v) for k, v in groups.items() if k not in sr.EXTRA_GROUPS]
    for name, members in ordered:
        if symbol in members:
            others = [m for m in members if m != symbol and _plain(m)]
            return name, others[:limit]
    return None, []


def parse_peers(raw: str, symbol: str) -> list[str]:
    """Caller-supplied peers: plain tickers only, no repeats, never the
    symbol itself, capped."""
    out: list[str] = []
    for part in (raw or "").replace(";", ",").replace(" ", ",").split(","):
        s = part.strip().upper()
        if s and _plain(s) and s != symbol and s not in out:
            out.append(s)
    return out[:MAX_PEERS]


def _in_progress(last: date, now: datetime | None = None) -> bool:
    """True while the newest bar is today's and the session has not closed,
    so the last row is still changing."""
    now = (now or datetime.now(ET)).astimezone(ET)
    return last == now.date() and now.time() < dtime(16, 15)


def _news_window(prev_day: date, day: date) -> tuple[datetime, datetime]:
    """From the previous session's close to this session's close: the news
    that could have moved the price that day, including overnight."""
    return (datetime.combine(prev_day, dtime(16, 0), tzinfo=ET),
            datetime.combine(day, dtime(16, 0), tzinfo=ET))


def recent_performance(symbol: str, sessions: int = 10, peers: list[str] | None = None) -> dict:
    """Full answer for one symbol. Never raises: returns data_ok False with a
    note when the bars cannot be read."""
    symbol = (symbol or "").strip().upper()
    sessions = max(MIN_SESSIONS, min(MAX_SESSIONS, int(sessions)))
    if not _plain(symbol):
        return {"symbol": symbol, "data_ok": False,
                "note": "Recent performance covers US-listed stocks and ETFs with plain tickers."}

    if peers:
        group, peer_list = "custom", [p for p in peers if p != symbol][:MAX_PEERS]
    else:
        group, peer_list = peers_for(symbol)
    compare = list(dict.fromkeys(peer_list + ([MARKET] if symbol != MARKET else [])))

    key = (symbol, sessions, tuple(compare))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]

    from src.data import client
    try:
        bars = client.get_multi_bars([symbol] + compare, days=_HISTORY_DAYS)
    except Exception as e:
        logger.warning("Recent performance bars failed for %s: %s", symbol, str(e)[:160])
        return {"symbol": symbol, "data_ok": False, "note": "Price history could not be loaded."}

    summary = summarize(bars.get(symbol), sessions)
    if summary is None:
        return {"symbol": symbol, "data_ok": False, "note": f"No recent price history for {symbol}."}

    base, last = date.fromisoformat(summary["base_date"]), date.fromisoformat(summary["last_date"])
    compared = []
    for p in compare:
        chg = change_between(bars.get(p), base, last)
        if chg is not None:
            compared.append({"symbol": p, "change_pct": chg, "is_market": p == MARKET})

    # Headlines for the biggest days. News is decoration: a failure leaves
    # the table intact and is reported as unavailable, not as "no news".
    from src.data import news
    rows = summary["rows"]
    events = []
    for i, r in enumerate(rows):
        if not r["big"]:
            continue
        prev = date.fromisoformat(rows[i - 1]["date"]) if i > 0 else base
        start, end = _news_window(prev, date.fromisoformat(r["date"]))
        try:
            heads = news.headlines_between(symbol, start, end, limit=3)
        except Exception:
            heads = None
        events.append({"date": r["date"], "change_pct": r["change_pct"], "rvol": r["rvol"],
                       "headlines": heads})

    result = {
        "symbol": symbol,
        "data_ok": True,
        "note": None,
        **summary,
        "in_progress": _in_progress(last),
        "peer_group": group,
        "compared": compared,
        "big_days": events,
        "big_day_rule": (f"at least {_BIG_DAY_MULT:g} times its normal daily move "
                         f"({summary['typical_move']}%)") if summary["typical_move"] else None,
    }
    from src.data.news import _bounded_put
    _bounded_put(_cache, key, (time.time(), result), _CACHE_MAX)
    return result
