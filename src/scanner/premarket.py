"""Pre-market gap list.

Stocks trading well away from yesterday's close before the open, on enough
volume to mean something, with the reason attached where there is one.

A gap on a few thousand shares is noise, so a row needs both an absolute
share count and a meaningful slice of the stock's normal day already traded.
The universe is the watch universe plus companies that reported last night
or this morning, since those are the names that gap.

After the open the list stays up (it is the day's gap list) and each row
also shows where the stock is now, so you can see whether the gap held.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd

from src.data import client
from src.data import earnings_calendar as ec

logger = logging.getLogger("mse.premarket")

ET = ZoneInfo("America/New_York")
PRE_OPEN = dtime(4, 0)
OPEN = dtime(9, 30)
CLOSE = dtime(16, 0)
_CACHE_TTL = 2 * 60
_MAX_UNIVERSE = 500
_cache: dict[str, tuple[float, dict]] = {}


def _reporters(today) -> dict[str, dict]:
    """Companies that reported after yesterday's close or before today's
    open (market cap $1B+). Empty if the calendar cannot be read."""
    from src.scanner.catalyst_watch import _trading_days
    from src.scanner.spike_reversal import _plain

    out: dict[str, dict] = {}
    previous = _trading_days(today, 1, -1)[0]
    for day, sessions in ((previous, ("amc", "")), (today, ("bmo", ""))):
        try:
            rows = ec.nasdaq_day(day) or []
        except Exception as e:
            logger.debug("Pre-market: calendar unavailable for %s: %s", day, e)
            rows = []
        for r in rows:
            if not _plain(r["symbol"]) or (r.get("market_cap") or 0) < 1e9:
                continue
            if ec.session_label(r.get("time", "")) in sessions:
                out.setdefault(r["symbol"], {**r, "earnings_date": day.isoformat()})
    return out


def premarket_stats(bars: pd.DataFrame, today) -> dict | None:
    """Last price, volume and range of today's 04:00-09:30 ET bars, plus the
    latest price of the day (which is after the open once it has opened)."""
    if bars is None or bars.empty:
        return None
    idx = pd.to_datetime(bars.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    b = bars.copy()
    b.index = idx.tz_convert(ET)
    b = b.sort_index()
    day = b[b.index.date == today]
    pre = day[(day.index.time >= PRE_OPEN) & (day.index.time < OPEN)]
    if pre.empty:
        return None
    regular = day[(day.index.time >= OPEN) & (day.index.time < CLOSE)]
    return {
        "pre_last": float(pre["close"].iloc[-1]),
        "pre_high": float(pre["high"].max()),
        "pre_low": float(pre["low"].min()),
        "pre_volume": int(pre["volume"].sum()),
        "pre_time": pre.index[-1].isoformat(),
        "open_price": float(regular["open"].iloc[0]) if not regular.empty else None,
        "now_price": float(day["close"].iloc[-1]),
    }


def scan_premarket_gaps(
    symbols: list[str] | None = None,
    min_gap_pct: float = 2.0,
    min_volume: int = 5_000,
    min_day_share_pct: float = 0.3,
    with_news: bool = True,
    now: datetime | None = None,
) -> dict:
    """Stocks gapping `min_gap_pct`+ before the open on real volume.

    `min_day_share_pct` is the pre-market volume as a percentage of the
    stock's average full-day volume: 0.3 means a third of a percent of a
    normal day has already traded. That relative test does the real work;
    the absolute floor only removes a handful of odd-lot prints. (A fixed
    20,000-share floor hid a 21% earnings gap in a stock that had already
    traded 1% of its day at 6 AM.)
    """
    key = f"{min_gap_pct}_{min_volume}_{min_day_share_pct}_{'d' if symbols is None else len(symbols)}"
    cached = _cache.get(key)
    if now is None and cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]

    n = (now or datetime.now(tz=ET)).astimezone(ET)
    today = n.date()
    base = {"gaps": [], "data_ok": True, "notes": [], "phase": "",
            "as_of": n.isoformat(timespec="minutes")}

    if n.weekday() >= 5:
        return {**base, "phase": "closed", "notes": ["Weekend: no pre-market session."]}
    if n.time() < PRE_OPEN:
        return {**base, "phase": "closed",
                "notes": ["Pre-market trading starts at 4:00 AM ET."]}
    phase = "premarket" if n.time() < OPEN else ("open" if n.time() < CLOSE else "after")

    from src.scanner.spike_reversal import _plain, default_universe
    reporters = _reporters(today)
    universe = [s for s in (symbols or default_universe()) if _plain(s)]
    universe = list(dict.fromkeys(universe + list(reporters)))[:_MAX_UNIVERSE]

    minutes = (n.hour - PRE_OPEN.hour) * 60 + n.minute + 15
    try:
        daily = client.get_multi_bars(universe, days=45)
        intraday = client.get_intraday_multi_bars(
            universe, minutes_back=minutes, timeframe_minutes=5
        )
    except Exception as e:
        logger.warning("Pre-market scan: price data unavailable: %s", str(e)[:160])
        return {**base, "phase": phase, "data_ok": False, "notes": ["Price data unavailable."]}

    rows: list[dict] = []
    for sym in universe:
        try:
            d = daily.get(sym)
            if d is None or len(d) < 5:
                continue
            d = d.sort_index()
            prior = d[pd.to_datetime(d.index).date < today]
            if prior.empty:
                continue
            prior_close = float(prior["close"].iloc[-1])
            avg_volume = float(prior["volume"].tail(20).mean())
            stats = premarket_stats(intraday.get(sym), today)
            if not stats or prior_close <= 0 or avg_volume <= 0:
                continue
            gap = (stats["pre_last"] / prior_close - 1) * 100
            day_share = stats["pre_volume"] / avg_volume * 100
            if (abs(gap) < min_gap_pct or stats["pre_volume"] < min_volume
                    or day_share < min_day_share_pct):
                continue
            cal = reporters.get(sym)
            rows.append({
                "symbol": sym,
                "direction": "up" if gap > 0 else "down",
                "gap_pct": round(gap, 2),
                "prior_close": round(prior_close, 2),
                "price": round(stats["pre_last"], 2),
                "pre_high": round(stats["pre_high"], 2),
                "pre_low": round(stats["pre_low"], 2),
                "pre_volume": stats["pre_volume"],
                "day_share_pct": round(day_share, 2),
                "time": stats["pre_time"],
                "open_price": round(stats["open_price"], 2) if stats["open_price"] else None,
                # Where it is now, as a change from yesterday's close. Equal to
                # the gap until the market opens.
                "now_pct": round((stats["now_price"] / prior_close - 1) * 100, 2),
                "reported": bool(cal),
                "surprise_pct": cal.get("surprise_pct") if cal else None,
                "name": cal.get("name", "") if cal else "",
            })
        except Exception as e:
            logger.debug("Pre-market scan failed for %s: %s", sym, e)

    rows.sort(key=lambda r: abs(r["gap_pct"]), reverse=True)

    if with_news and rows:
        from src.data.news import latest_headlines
        news = latest_headlines([r["symbol"] for r in rows[:40]], hours=20)
        for r in rows:
            top = (news.get(r["symbol"]) or [None])[0]
            r["headline"] = top["headline"] if top else ""

    notes = []
    # Say how old the data is. Alpaca's free plan delays full-market bars by
    # 15 minutes, so a "9:15 list" really shows about 9:00.
    newest = max((r["time"] for r in rows), default="")
    delay = None
    if newest:
        delay = int((n - datetime.fromisoformat(newest)).total_seconds() // 60) - 5
        if phase == "premarket" and delay >= 10:
            notes.append(f"Prices are about {delay} minutes behind: the data plan delays "
                         "full-market bars.")
    if phase != "premarket":
        notes.append("The market has opened: this is this morning's gap list, with where "
                     "each stock is now.")
    result = {**base, "gaps": rows, "phase": phase, "notes": notes,
              "universe": len(universe), "reporters": len(reporters),
              "data_as_of": newest, "delay_minutes": delay}
    if now is None:
        _cache[key] = (time.time(), result)
    return result


def scorecard_alerts(result: dict) -> list[dict]:
    """Gaps as scorecard alerts: kind premarket_gap in the gap's direction,
    so a positive outcome means the gap kept going."""
    return [
        {"symbol": r["symbol"], "kind": "premarket_gap", "direction": r["direction"],
         "price": r["price"], "time": r["time"]}
        for r in result.get("gaps", [])
    ]
