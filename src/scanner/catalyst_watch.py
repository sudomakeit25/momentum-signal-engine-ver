"""Catalyst watch: stocks set up to move hard on a scheduled event, and
stocks that just did.

Two lists, for two different ways of working:

  upcoming  Earnings in the next few trading days AND short sellers who
            would need days to buy back. These are the conditions under
            which a surprise produces an outsized move. They say nothing
            about direction: the same setup falls hard on a bad report.

  reacting  Reported in the last few trading days and answered with a big
            up day on several times normal volume. The direction is known;
            the first leg has already happened.

Sources: Nasdaq's earnings calendar (who reports when; for past dates also
the reported EPS and surprise), FINRA's bi-monthly consolidated short
interest, and daily bars from Alpaca. The universe is whoever is on the
earnings calendar, not the app's built-in symbol list, so names outside
that list are found too.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src.data import client
from src.data import earnings_calendar as ec

logger = logging.getLogger("mse.catalyst_watch")

ET = ZoneInfo("America/New_York")
_PLAIN_SYMBOL = re.compile(r"^[A-Z]{1,5}$")
_CACHE_TTL = 30 * 60
_MAX_UPCOMING = 400       # symbols priced for the upcoming list
_MAX_REACTING = 1500      # a busy earnings week has well over 1,000 reporters

_cache: dict[str, tuple[float, dict]] = {}


def _trading_days(start: date, count: int, step: int) -> list[date]:
    """`count` weekdays from `start` going forward (step=1, start included)
    or backward (step=-1, start excluded). Exchange holidays are not known
    here; the calendar simply returns nobody for them."""
    out: list[date] = []
    d = start if step > 0 else start - timedelta(days=1)
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=step)
    return out


def _tradeable() -> set[str] | None:
    try:
        return {a["symbol"] for a in client.get_tradeable_assets()}
    except Exception as e:
        # The SDK rejects the whole list when Alpaca adds an exchange code it
        # does not know. The symbol-shape check below is the fallback.
        logger.warning("Catalyst watch: asset list unavailable (%s): %s",
                       type(e).__name__, str(e).splitlines()[0][:120])
        return None


def _usable(symbol: str, tradeable: set[str] | None) -> bool:
    if not _PLAIN_SYMBOL.match(symbol):
        return False          # share classes, warrants, foreign listings
    return tradeable is None or symbol in tradeable


def _f(value, digits: int = 2) -> float:
    return round(float(value), digits)


def price_stats(df: pd.DataFrame) -> dict | None:
    """Price position and volume from daily bars (oldest first)."""
    if df is None or len(df) < 25:
        return None
    df = df.sort_index()
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    last = float(close.iloc[-1])
    if last <= 0:
        return None
    window = df.tail(63)                       # about 3 months
    low, high = float(window["low"].min()), float(window["high"].max())
    span = high - low
    avg_vol = float(vol.iloc[-21:-1].mean())
    return {
        "price": _f(last),
        "chg_5d": _f((last / float(close.iloc[-6]) - 1) * 100) if len(close) >= 6 else 0.0,
        "low_3m": _f(low),
        "high_3m": _f(high),
        # 0 = sitting on the 3-month low, 100 = at the 3-month high
        "range_pos": _f((last - low) / span * 100, 1) if span > 0 else 50.0,
        "avg_volume": int(avg_vol),
        "last_day_pct": _f((last / float(close.iloc[-2]) - 1) * 100),
        "last_day_rvol": _f(float(vol.iloc[-1]) / avg_vol, 1) if avg_vol > 0 else 0.0,
    }


def coiled_score(days_to_cover: float, si_change_pct: float, range_pos: float,
                 days_until: int) -> float:
    """0-100: how much stored energy there is, NOT which way it goes.

      35  days to cover (trapped shorts), full at 10 days
      20  short interest rose since the last report, full at +20%
      25  price near its 3-month low, full at the low
      20  the event is close, full if today or tomorrow
    """
    dtc = 35.0 * min(max(days_to_cover, 0.0) / 10.0, 1.0)
    building = 20.0 * min(max(si_change_pct, 0.0) / 20.0, 1.0)
    depressed = 25.0 * (1.0 - min(max(range_pos, 0.0), 100.0) / 100.0)
    soon = 20.0 * max(0.0, 1.0 - max(days_until - 1, 0) / 5.0)
    return round(dtc + building + depressed + soon, 1)


def best_reaction(df: pd.DataFrame, since: date) -> dict | None:
    """The strongest up day on or after `since`: its date, move and volume
    multiple, and how price has done since that day's close."""
    if df is None or len(df) < 25:
        return None
    df = df.sort_index()
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    best = None
    for i in range(len(df) - 1, 21, -1):
        day = pd.Timestamp(df.index[i]).date()
        if day < since:
            break
        prev = float(close.iloc[i - 1])
        avg = float(vol.iloc[i - 20:i].mean())
        if prev <= 0 or avg <= 0:
            continue
        pct = (float(close.iloc[i]) / prev - 1) * 100
        rvol = float(vol.iloc[i]) / avg
        if best is None or pct > best["reaction_pct"]:
            best = {
                "reaction_date": day.isoformat(),
                "reaction_pct": _f(pct),
                "reaction_rvol": _f(rvol, 1),
                "since_reaction_pct": _f((float(close.iloc[-1]) / float(close.iloc[i]) - 1) * 100),
            }
    return best


def scan_catalyst_watch(
    days_ahead: int = 5,
    days_back: int = 5,
    min_days_to_cover: float = 3.0,
    min_price: float = 5.0,
    min_avg_volume: int = 500_000,
    min_market_cap: float = 300_000_000,
    min_reaction_pct: float = 5.0,
    min_reaction_rvol: float = 2.0,
    now: datetime | None = None,
) -> dict:
    """Build both lists. Returns {upcoming, reacting, data_ok, notes, ...}."""
    cache_key = (f"{days_ahead}_{days_back}_{min_days_to_cover}_{min_price}_"
                 f"{min_avg_volume}_{min_market_cap}_{min_reaction_pct}_{min_reaction_rvol}")
    cached = _cache.get(cache_key)
    if now is None and cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]

    today = (now or datetime.now(tz=ET)).astimezone(ET).date()
    notes: list[str] = []
    tradeable = _tradeable()

    # ---- who reports, and who just did
    ahead: dict[str, dict] = {}
    for n, day in enumerate(_trading_days(today, days_ahead, 1)):
        rows = ec.nasdaq_day(day)
        if rows is None:
            notes.append(f"Earnings calendar unavailable for {day.isoformat()}.")
            continue
        for r in rows:
            ahead.setdefault(r["symbol"], {**r, "earnings_date": day.isoformat(), "days_until": n})
    behind: dict[str, dict] = {}
    for day in _trading_days(today, days_back, -1):
        rows = ec.nasdaq_day(day)
        if rows is None:
            notes.append(f"Earnings calendar unavailable for {day.isoformat()}.")
            continue
        for r in rows:
            behind.setdefault(r["symbol"], {**r, "earnings_date": day.isoformat()})

    def big_enough(r: dict) -> bool:
        cap = r.get("market_cap")
        return cap is None or cap >= min_market_cap

    # ---- short interest
    from src.data.finra_client import get_short_interest
    try:
        short_interest = get_short_interest() or {}
    except Exception as e:
        logger.warning("Catalyst watch: short interest unavailable: %s", e)
        short_interest = {}
    if not short_interest:
        notes.append("FINRA short interest unavailable, so the upcoming list is empty.")

    upcoming_syms = [
        s for s, r in ahead.items()
        if _usable(s, tradeable) and big_enough(r)
        and float(short_interest.get(s, {}).get("days_to_cover", 0.0) or 0.0) >= min_days_to_cover
    ]
    reacting_syms = sorted(
        (s for s, r in behind.items() if _usable(s, tradeable) and big_enough(r)),
        key=lambda s: behind[s].get("market_cap") or 0.0, reverse=True,
    )

    upcoming_syms = upcoming_syms[:_MAX_UPCOMING]
    if len(reacting_syms) > _MAX_REACTING:
        notes_dropped = len(reacting_syms) - _MAX_REACTING
        logger.info("Catalyst watch: %d smallest reporters not priced", notes_dropped)
        reacting_syms = reacting_syms[:_MAX_REACTING]

    bars: dict[str, pd.DataFrame] = {}
    try:
        if upcoming_syms:
            # 3-month range needs about 63 sessions
            bars.update(client.get_multi_bars(upcoming_syms, days=130))
        rest = [s for s in reacting_syms if s not in bars]
        if rest:
            # 20-day average volume plus the reaction window is enough here
            bars.update(client.get_multi_bars(rest, days=70))
    except Exception as e:
        logger.warning("Catalyst watch: price data unavailable: %s", str(e)[:200])
        notes.append("Price data unavailable.")

    # ---- upcoming: coiled before the event
    upcoming: list[dict] = []
    for sym in upcoming_syms:
        stats = price_stats(bars.get(sym))
        if not stats or stats["price"] < min_price or stats["avg_volume"] < min_avg_volume:
            continue
        cal, si = ahead[sym], short_interest[sym]
        dtc = float(si.get("days_to_cover", 0.0) or 0.0)
        si_chg = float(si.get("change_pct", 0.0) or 0.0)
        upcoming.append({
            "symbol": sym,
            "name": cal.get("name", ""),
            "earnings_date": cal["earnings_date"],
            "session": ec.session_label(cal.get("time", "")),
            "days_until": int(cal["days_until"]),
            "market_cap": cal.get("market_cap"),
            "days_to_cover": _f(dtc),
            "shares_short": int(si.get("shares_short", 0) or 0),
            "si_change_pct": _f(si_chg, 1),
            "settlement_date": si.get("settlement_date", ""),
            **stats,
            # A sharp up day on heavy volume before the report: someone is early
            "early_move": bool(stats["last_day_pct"] >= min_reaction_pct
                               and stats["last_day_rvol"] >= min_reaction_rvol),
            "score": coiled_score(dtc, si_chg, stats["range_pos"], int(cal["days_until"])),
        })
    upcoming.sort(key=lambda r: r["score"], reverse=True)

    # ---- reacting: reported, and the market liked it
    reacting: list[dict] = []
    for sym in reacting_syms:
        df = bars.get(sym)
        stats = price_stats(df)
        if not stats or stats["price"] < min_price or stats["avg_volume"] < min_avg_volume:
            continue
        cal = behind[sym]
        # An after-close report is answered the next session; a day of
        # slack before the date also catches a run-up into the report.
        since = date.fromisoformat(cal["earnings_date"]) - timedelta(days=1)
        reaction = best_reaction(df, since)
        if (not reaction or reaction["reaction_pct"] < min_reaction_pct
                or reaction["reaction_rvol"] < min_reaction_rvol):
            continue
        si = short_interest.get(sym, {})
        reacting.append({
            "symbol": sym,
            "name": cal.get("name", ""),
            "earnings_date": cal["earnings_date"],
            "session": ec.session_label(cal.get("time", "")),
            "market_cap": cal.get("market_cap"),
            "eps": cal.get("eps"),
            "eps_forecast": cal.get("eps_forecast"),
            "surprise_pct": cal.get("surprise_pct"),
            "days_to_cover": _f(float(si.get("days_to_cover", 0.0) or 0.0)),
            "si_change_pct": _f(float(si.get("change_pct", 0.0) or 0.0), 1),
            **stats,
            **reaction,
        })
    reacting.sort(key=lambda r: r["reaction_pct"] * min(r["reaction_rvol"], 6.0), reverse=True)

    settlement = next(iter(short_interest.values()), {}).get("settlement_date", "") \
        if short_interest else ""
    result = {
        "upcoming": upcoming,
        "reacting": reacting,
        "data_ok": not notes,
        "notes": notes,
        "as_of": datetime.now(tz=ET).isoformat(timespec="minutes"),
        "short_interest_date": settlement,
        "calendar_symbols": {"upcoming": len(ahead), "reported": len(behind)},
    }
    if now is None and not notes:
        _cache[cache_key] = (time.time(), result)
    return result
