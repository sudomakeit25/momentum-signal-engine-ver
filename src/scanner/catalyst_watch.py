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
_MAX_HISTORY = 160        # companies whose past earnings reactions are looked up

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
    # A year's range, when there is most of a year of history. A stock can sit
    # at its 3-month high and still be near the bottom of its year.
    low_52w = high_52w = pos_52w = None
    if len(df) >= 200:
        year = df.tail(252)
        low_52w, high_52w = float(year["low"].min()), float(year["high"].max())
        if high_52w > low_52w:
            pos_52w = _f((last - low_52w) / (high_52w - low_52w) * 100, 1)
    return {
        "price": _f(last),
        "chg_5d": _f((last / float(close.iloc[-6]) - 1) * 100) if len(close) >= 6 else 0.0,
        "low_3m": _f(low),
        "high_3m": _f(high),
        # 0 = sitting on the 3-month low, 100 = at the 3-month high
        "range_pos": _f((last - low) / span * 100, 1) if span > 0 else 50.0,
        "low_52w": _f(low_52w) if low_52w is not None else None,
        "high_52w": _f(high_52w) if high_52w is not None else None,
        "range_pos_52w": pos_52w,
        "avg_volume": int(avg_vol),
        "last_day_pct": _f((last / float(close.iloc[-2]) - 1) * 100),
        "last_day_rvol": _f(float(vol.iloc[-1]) / avg_vol, 1) if avg_vol > 0 else 0.0,
    }


def coiled_score(days_to_cover: float, si_change_pct: float, range_pos: float,
                 days_until: int, range_pos_52w: float | None = None) -> float:
    """0-100: how much stored energy there is, NOT which way it goes.

      35  days to cover (trapped shorts), full at 10 days
      20  short interest rose since the last report, full at +20%
      25  price is beaten down: the average of where it sits in its 3-month
          and 52-week ranges, full at the low of both
      20  the event is close, full if today or tomorrow
    """
    dtc = 35.0 * min(max(days_to_cover, 0.0) / 10.0, 1.0)
    building = 20.0 * min(max(si_change_pct, 0.0) / 20.0, 1.0)
    positions = [range_pos] + ([range_pos_52w] if range_pos_52w is not None else [])
    position = sum(min(max(p, 0.0), 100.0) for p in positions) / len(positions)
    depressed = 25.0 * (1.0 - position / 100.0)
    soon = 20.0 * max(0.0, 1.0 - max(days_until - 1, 0) / 5.0)
    return round(dtc + building + depressed + soon, 1)


def past_reactions(df: pd.DataFrame, history: list[dict] | None, session: str = "",
                   limit: int = 4) -> list[dict] | None:
    """How the stock moved in the first session after each past report.

    A report after the close is answered the next session, one before the
    open the same session. The company's usual timing is taken from the
    upcoming report (`session`); when it is unknown, the larger of the two
    candidate days is used. Returns None when the history is unavailable,
    and skips reports the price data does not cover.
    """
    if history is None or df is None or len(df) < 3:
        return None
    df = df.sort_index()
    idx = pd.to_datetime(df.index)
    days = [ts.date() for ts in (idx.tz_convert("UTC") if idx.tz is not None else idx)]
    closes = df["close"].astype(float).tolist()

    def move(i: int) -> float | None:
        if 1 <= i < len(closes) and closes[i - 1] > 0:
            return (closes[i] / closes[i - 1] - 1) * 100
        return None

    out = []
    for h in history:
        try:
            reported = date.fromisoformat(h["date"])
        except (KeyError, ValueError):
            continue
        i = next((k for k, d in enumerate(days) if d >= reported), None)
        # The matched session must be the report's own (allowing a weekend or
        # holiday). A report older than the price history would otherwise be
        # pinned to the first bar and credited with an unrelated move.
        if i is None or (days[i] - reported).days > 5:
            continue
        same_day, next_day = move(i), move(i + 1)
        if session == "amc":
            chosen, j = next_day, i + 1
        elif session == "bmo":
            chosen, j = same_day, i
        else:
            options = [(m, k) for m, k in ((same_day, i), (next_day, i + 1)) if m is not None]
            chosen, j = max(options, key=lambda x: abs(x[0])) if options else (None, i)
        if chosen is None:
            continue
        out.append({"date": h["date"], "reaction_date": days[j].isoformat(),
                    "move_pct": _f(chosen), "surprise_pct": h.get("surprise_pct")})
        if len(out) >= limit:
            break
    return out


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
    min_excess_pct: float = 4.0,
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
            # A year of sessions: the 52-week range and a year of past
            # earnings reactions. SPY rides along as the market yardstick.
            bars.update(client.get_multi_bars(upcoming_syms + ["SPY"], days=400))
        rest = [s for s in reacting_syms if s not in bars]
        if rest:
            # 20-day average volume plus the reaction window is enough here
            bars.update(client.get_multi_bars(rest, days=70))
    except Exception as e:
        logger.warning("Catalyst watch: price data unavailable: %s", str(e)[:200])
        notes.append("Price data unavailable.")

    # What the market itself did in the last session. A stock that merely
    # rose with a strong tape has not made an "early move".
    market = price_stats(bars.get("SPY"))
    market_pct = market["last_day_pct"] if market else 0.0

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
            "last_day_vs_market": _f(stats["last_day_pct"] - market_pct),
            # A sharp up day on heavy volume that the market does not explain
            "early_move": bool(
                stats["last_day_pct"] >= min_reaction_pct
                and stats["last_day_rvol"] >= min_reaction_rvol
                and stats["last_day_pct"] - market_pct >= min_excess_pct
            ),
            "score": coiled_score(dtc, si_chg, stats["range_pos"], int(cal["days_until"]),
                                  stats.get("range_pos_52w")),
            "past_reactions": None,
            "typical_move_pct": None,
        })
    upcoming.sort(key=lambda r: r["score"], reverse=True)

    # Past earnings reactions for the highest-scored names (one request per
    # company, so it is capped; history is cached for a week).
    def _attach(row: dict) -> None:
        try:
            reactions = past_reactions(
                bars.get(row["symbol"]), ec.earnings_history(row["symbol"]), row["session"]
            )
        except Exception as e:
            logger.debug("Past reactions failed for %s: %s", row["symbol"], e)
            reactions = None
        row["past_reactions"] = reactions
        if reactions:
            row["typical_move_pct"] = _f(
                sum(abs(r["move_pct"]) for r in reactions) / len(reactions), 1
            )

    if upcoming:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(_attach, upcoming[:_MAX_HISTORY]))

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
