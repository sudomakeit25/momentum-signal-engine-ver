"""Sudden spikes and reversals.

Spikes
  volume_ignition    a 5-minute bar trading several times its usual volume
                     for that time of day, closing through yesterday's
                     high (or low): the first sign of an abnormal move
  sympathy           one stock in a peer group is up sharply and others in
                     the group have not moved yet

Reversals
  failed_breakout    closed above yesterday's high, then back below it
  failed_breakdown   closed below yesterday's low, then back above it
  exhaustion_top     after a steep run, a very heavy day that closes near
                     its low
  capitulation_low   after a steep fall, a very heavy day that closes near
                     its high

Context
  stretched          far above or below where it was a week ago; no signal,
                     just the names where a reversal is most worth watching

These are detections, not predictions. Every event is logged to the
scorecard so their actual follow-through can be measured before any of
them is trusted or turned into an alert.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.data import client

logger = logging.getLogger("mse.spike_reversal")

ET = ZoneInfo("America/New_York")
_CACHE_TTL = 3 * 60
_cache: dict[str, tuple[float, dict]] = {}

# Peer groups for sympathy moves. A leader's news often reprices the group.
EXTRA_GROUPS: dict[str, list[str]] = {
    "crypto_miners": ["RIOT", "MARA", "CLSK", "HUT", "IREN", "CIFR", "WULF", "CORZ", "BTDR", "BITF"],
    "crypto_exchanges": ["COIN", "HOOD", "MSTR", "GLXY"],
    "memory_storage": ["MU", "SNDK", "WDC", "STX"],
    "space": ["ASTS", "RKLB", "LUNR", "PL", "RDW"],
}


def peer_groups() -> dict[str, list[str]]:
    from src.scanner.profile_screener import SECTORS
    return {**{k: list(v) for k, v in SECTORS.items()}, **EXTRA_GROUPS}


def default_universe() -> list[str]:
    from src.scanner.intraday_movers import _intraday_universe
    names = list(_intraday_universe(None))
    for members in peer_groups().values():
        names.extend(members)
    return [s for s in dict.fromkeys(names) if _plain(s)]


def _plain(symbol: str) -> bool:
    """Alpaca rejects a whole batch if one symbol is malformed for it (for
    example BRK-B), so only plain 1-5 letter tickers are requested."""
    return symbol.isalpha() and symbol.isupper() and 1 <= len(symbol) <= 5


# ------------------------------------------------------------ volume profile

# symbol -> {"HH:MM": median 5-minute volume at that time of day}
_profile: dict[str, dict[str, float]] = {}
_profile_date = ""


def build_volume_profile(bars_5m: dict[str, pd.DataFrame], today) -> dict[str, dict[str, float]]:
    """Median volume per 5-minute slot over past sessions (today excluded)."""
    out: dict[str, dict[str, float]] = {}
    for sym, df in bars_5m.items():
        if df is None or df.empty:
            continue
        idx = pd.to_datetime(df.index)
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        local = idx.tz_convert(ET)
        frame = pd.DataFrame({"volume": df["volume"].to_numpy(dtype=float)}, index=local)
        frame = frame[(frame.index.date < today)]
        mins = frame.index.hour * 60 + frame.index.minute
        frame = frame[(mins >= 570) & (mins < 960)]
        if frame.index.normalize().nunique() < 5:
            continue          # too few sessions to call anything "usual"
        slots = frame.groupby(frame.index.strftime("%H:%M"))["volume"].median()
        out[sym] = {k: float(v) for k, v in slots.items()}
    return out


_PROFILE_KEY = "mse:volume_profile"
# Symbols fetched per request while building the profile. Fetching all ~90
# at once held about 260,000 five-minute bars and took the process from
# 88 MB to 479 MB, past the host's 512 MB once other scans ran alongside.
_PROFILE_CHUNK = 8
_PROFILE_DAYS = 21          # about 15 sessions: a stable median per slot
_PROFILE_RETRY = 30 * 60    # after a failed build, wait this long before trying again
_profile_failed_at = 0.0


def _load_saved_profile(today_iso: str) -> dict[str, dict[str, float]] | None:
    """Today's profile from Redis, so a restart does not rebuild it."""
    try:
        import json
        from src.data.redis_store import _get_redis
        redis = _get_redis()
        if not redis:
            return None
        raw = redis.get(_PROFILE_KEY)
        if not raw:
            return None
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict) or data.get("date") != today_iso:
            return None
        return {str(s): {str(k): float(v) for k, v in slots.items()}
                for s, slots in (data.get("profile") or {}).items()}
    except Exception as e:
        logger.warning("Saved volume profile unreadable: %s", str(e)[:160])
        return None


def _save_profile(today_iso: str, profile: dict[str, dict[str, float]]) -> None:
    try:
        import json
        from src.data.redis_store import _get_redis
        redis = _get_redis()
        if redis:
            redis.set(_PROFILE_KEY, json.dumps({"date": today_iso, "profile": profile}))
    except Exception as e:
        logger.warning("Volume profile not saved: %s", str(e)[:160])


def ensure_volume_profile(symbols: list[str], now: datetime | None = None) -> bool:
    """Make today's profile available: from memory, else from Redis, else
    built a few symbols at a time and saved. Returns whether one exists."""
    global _profile, _profile_date, _profile_failed_at
    today = (now or datetime.now(tz=ET)).astimezone(ET).date()
    today_iso = today.isoformat()
    if _profile_date == today_iso and _profile:
        return True
    saved = _load_saved_profile(today_iso)
    if saved:
        _profile, _profile_date = saved, today_iso
        logger.info("Volume profile loaded for %d symbols", len(saved))
        return True
    if time.time() - _profile_failed_at < _PROFILE_RETRY:
        return False
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    wanted = [s for s in dict.fromkeys(symbols) if _plain(s)]
    built: dict[str, dict[str, float]] = {}
    failed = 0
    for i in range(0, len(wanted), _PROFILE_CHUNK):
        chunk = wanted[i:i + _PROFILE_CHUNK]
        try:
            raw = client.get_multi_bars(
                chunk, timeframe=TimeFrame(5, TimeFrameUnit.Minute), days=_PROFILE_DAYS
            )
            built.update(build_volume_profile(raw, today))
            del raw
        except Exception as e:
            failed += 1
            logger.warning("Volume profile chunk failed (%s...): %s", chunk[0], str(e)[:160])
    if not built:
        _profile_failed_at = time.time()
        logger.warning("Volume profile unavailable; retrying in %d minutes", _PROFILE_RETRY // 60)
        return False
    _profile, _profile_date = built, today_iso
    _save_profile(today_iso, built)
    logger.info("Volume profile built for %d symbols (%d chunks failed)", len(built), failed)
    return True


def profile_ready(now: datetime | None = None) -> bool:
    today = (now or datetime.now(tz=ET)).astimezone(ET).date().isoformat()
    return bool(_profile) and _profile_date == today


# ---------------------------------------------------------------- detectors

def _event(symbol: str, kind: str, direction: str, price: float, when, detail: str,
           **extra) -> dict:
    return {
        "symbol": symbol, "kind": kind, "direction": direction,
        "price": round(float(price), 2),
        "time": when.isoformat() if hasattr(when, "isoformat") else str(when),
        "detail": detail, **extra,
    }


def detect_volume_ignition(
    symbol: str, sdf: pd.DataFrame, slots: dict[str, float] | None,
    prior_high: float, prior_low: float, min_multiple: float = 8.0,
) -> dict | None:
    """Latest 5-minute bar at `min_multiple` times its usual volume for
    that time of day, closing beyond yesterday's range in the bar's own
    direction.

    The default of 8x comes from replaying 2026-11-03..09 over ~240 symbols:
    5x fired about 67 times a day, 8x about 14, 12x about 3. That week was
    unusually volatile, so normal weeks should be quieter."""
    if sdf is None or len(sdf) < 2 or not slots:
        return None
    last = sdf.iloc[-1]
    usual = slots.get(sdf.index[-1].strftime("%H:%M"), 0.0)
    if usual < 1000:           # no meaningful baseline for this slot
        return None
    multiple = float(last["volume"]) / usual
    if multiple < min_multiple:
        return None
    o, c = float(last["open"]), float(last["close"])
    if c > o and prior_high > 0 and c > prior_high:
        return _event(symbol, "volume_ignition", "up", c, sdf.index[-1],
                      f"{multiple:.1f}x usual volume for this time, through yesterday's "
                      f"high {prior_high:.2f}", multiple=round(multiple, 1))
    if c < o and prior_low > 0 and c < prior_low:
        return _event(symbol, "volume_ignition", "down", c, sdf.index[-1],
                      f"{multiple:.1f}x usual volume for this time, through yesterday's "
                      f"low {prior_low:.2f}", multiple=round(multiple, 1))
    return None


def detect_failed_break(
    symbol: str, sdf: pd.DataFrame, prior_high: float, prior_low: float, lookback: int = 8,
    min_break_pct: float = 0.25,
) -> dict | None:
    """Closed at least `min_break_pct` beyond yesterday's high (low) within
    the last `lookback` bars, and has now closed back inside. A session that
    opened beyond the level is a gap, not a break, and is ignored.

    Price crossing yesterday's extreme by a few cents and coming back is
    routine, so a close clearly beyond the level is required. In the replay
    of 2026-11-03..09 the looser version fired about 60 times a day with no
    measurable follow-through; treat this one as unproven until the
    scorecard says otherwise."""
    if sdf is None or len(sdf) < 3 or prior_high <= 0 or prior_low <= 0:
        return None
    closes = sdf["close"].astype(float)
    session_open = float(sdf["open"].iloc[0])
    last = float(closes.iloc[-1])
    recent = closes.iloc[-(lookback + 1):-1]
    beyond = 1 + min_break_pct / 100
    if session_open < prior_high and (recent >= prior_high * beyond).any() and last < prior_high * 0.999:
        return _event(symbol, "failed_breakout", "down", last, sdf.index[-1],
                      f"Closed above yesterday's high {prior_high:.2f}, now back below it",
                      level=round(prior_high, 2))
    if session_open > prior_low and (recent <= prior_low / beyond).any() and last > prior_low * 1.001:
        return _event(symbol, "failed_breakdown", "up", last, sdf.index[-1],
                      f"Closed below yesterday's low {prior_low:.2f}, now back above it",
                      level=round(prior_low, 2))
    return None


def detect_exhaustion(
    symbol: str, daily: pd.DataFrame, run_pct: float = 25.0, fall_pct: float = 20.0,
    volume_multiple: float = 2.5,
) -> dict | None:
    """A very heavy day that rejects the direction of a steep 5-session run."""
    if daily is None or len(daily) < 27:
        return None
    d = daily.sort_index()
    hi, lo, cl = float(d["high"].iloc[-1]), float(d["low"].iloc[-1]), float(d["close"].iloc[-1])
    base = float(d["close"].iloc[-6])
    avg_vol = float(d["volume"].iloc[-21:-1].mean())
    if base <= 0 or avg_vol <= 0 or hi <= lo:
        return None
    multiple = float(d["volume"].iloc[-1]) / avg_vol
    if multiple < volume_multiple:
        return None
    position = (cl - lo) / (hi - lo)          # 0 = closed on the low, 1 = on the high
    when = pd.Timestamp(d.index[-1])
    run_up = (hi / base - 1) * 100
    run_down = (lo / base - 1) * 100
    if run_up >= run_pct and position <= 0.35:
        return _event(symbol, "exhaustion_top", "down", cl, when,
                      f"Up {run_up:.0f}% in 5 sessions at the high, then closed in the "
                      f"lower third on {multiple:.1f}x volume", multiple=round(multiple, 1))
    if run_down <= -fall_pct and position >= 0.65:
        return _event(symbol, "capitulation_low", "up", cl, when,
                      f"Down {abs(run_down):.0f}% in 5 sessions at the low, then closed in "
                      f"the upper third on {multiple:.1f}x volume", multiple=round(multiple, 1))
    return None


def stretched(symbol: str, daily: pd.DataFrame, threshold_pct: float = 30.0) -> dict | None:
    """More than `threshold_pct` from its close 5 sessions ago. Context only."""
    if daily is None or len(daily) < 7:
        return None
    d = daily.sort_index()
    cl, base = float(d["close"].iloc[-1]), float(d["close"].iloc[-6])
    if base <= 0:
        return None
    move = (cl / base - 1) * 100
    if abs(move) < threshold_pct:
        return None
    return {"symbol": symbol, "price": round(cl, 2), "move_5d_pct": round(move, 1),
            "direction": "up" if move > 0 else "down"}


def day_change(daily: pd.DataFrame) -> tuple[float, float] | None:
    """(today's % change, today's volume as a multiple of the 20-day average)."""
    if daily is None or len(daily) < 22:
        return None
    d = daily.sort_index()
    prev, cl = float(d["close"].iloc[-2]), float(d["close"].iloc[-1])
    avg = float(d["volume"].iloc[-21:-1].mean())
    if prev <= 0 or avg <= 0:
        return None
    return (cl / prev - 1) * 100, float(d["volume"].iloc[-1]) / avg


def find_sympathy(
    changes: dict[str, tuple[float, float]], groups: dict[str, list[str]],
    leader_pct: float = 8.0, leader_rvol: float = 1.5, laggard_pct: float = 2.0,
) -> list[dict]:
    """For each group with a leader up `leader_pct`+ on real volume, the
    members that have barely moved."""
    out = []
    for group, members in groups.items():
        known = [(s, *changes[s]) for s in members if s in changes]
        leaders = [(s, p, v) for s, p, v in known if p >= leader_pct and v >= leader_rvol]
        if not leaders:
            continue
        leader = max(leaders, key=lambda x: x[1])
        laggards = sorted(
            ({"symbol": s, "change_pct": round(p, 2)} for s, p, _ in known
             if s != leader[0] and abs(p) < laggard_pct),
            key=lambda r: r["symbol"],
        )
        if laggards:
            out.append({"group": group, "leader": leader[0],
                        "leader_change_pct": round(leader[1], 2),
                        "leader_rvol": round(leader[2], 1), "laggards": laggards})
    out.sort(key=lambda r: r["leader_change_pct"], reverse=True)
    return out


# --------------------------------------------------------------------- scan

def scan_spikes_reversals(
    symbols: list[str] | None = None, now: datetime | None = None, with_news: bool = True,
) -> dict:
    """Run every detector. Returns {events, stretched, sympathy, notes, ...}.
    `events` are the dated detections that the scorecard tracks."""
    key = "default" if symbols is None else ",".join(sorted(symbols))
    cached = _cache.get(key)
    if now is None and cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]

    from src.scanner.intraday_movers import is_market_hours, session_bars

    universe = [s for s in (symbols or default_universe()) if _plain(s)]
    notes: list[str] = []
    events: list[dict] = []
    stretched_rows: list[dict] = []
    changes: dict[str, tuple[float, float]] = {}

    try:
        daily = client.get_multi_bars(universe, days=130)
    except Exception as e:
        logger.warning("Spike scan: daily bars unavailable: %s", str(e)[:160])
        return {"events": [], "stretched": [], "sympathy": [], "data_ok": False,
                "notes": ["Price data unavailable."], "market_open": False,
                "as_of": datetime.now(tz=ET).isoformat(timespec="minutes")}

    open_now = is_market_hours(now)
    intraday: dict[str, pd.DataFrame] = {}
    if open_now:
        try:
            intraday = client.get_intraday_multi_bars(
                universe, minutes_back=400, timeframe_minutes=5
            )
        except Exception as e:
            logger.warning("Spike scan: intraday bars unavailable: %s", str(e)[:160])
            notes.append("Intraday data unavailable; only daily signals shown.")
        if not profile_ready(now):
            notes.append("Usual-volume profile is still loading; volume ignition is off for now.")
    else:
        notes.append("Market is closed: intraday signals (volume ignition, failed breaks) "
                     "resume at the open.")

    today = (now or datetime.now(tz=ET)).astimezone(ET).date()
    for sym in universe:
        d = daily.get(sym)
        if d is None or len(d) < 27:
            continue
        try:
            d = d.sort_index()
            chg = day_change(d)
            if chg:
                changes[sym] = chg
            for hit in (detect_exhaustion(sym, d),):
                if hit:
                    events.append(hit)
            s = stretched(sym, d)
            if s:
                stretched_rows.append(s)

            if open_now and sym in intraday:
                sdf = session_bars(intraday[sym], now=now)
                if len(sdf) >= 4:
                    prior = d[pd.to_datetime(d.index).date < today]
                    if not prior.empty:
                        ph, pl = float(prior["high"].iloc[-1]), float(prior["low"].iloc[-1])
                        for hit in (
                            detect_volume_ignition(sym, sdf, _profile.get(sym), ph, pl),
                            detect_failed_break(sym, sdf, ph, pl),
                        ):
                            if hit:
                                events.append(hit)
        except Exception as e:
            logger.debug("Spike scan failed for %s: %s", sym, e)

    sympathy = find_sympathy(changes, peer_groups())
    stretched_rows.sort(key=lambda r: abs(r["move_5d_pct"]), reverse=True)

    if with_news:
        from src.data.news import latest_headlines
        names = [e["symbol"] for e in events] + [r["symbol"] for r in stretched_rows[:15]] \
            + [r["leader"] for r in sympathy]
        news = latest_headlines(names) if names else {}
        for row in events + stretched_rows + sympathy:
            sym = row.get("symbol") or row.get("leader")
            top = (news.get(sym) or [None])[0]
            row["headline"] = top["headline"] if top else ""

    result = {
        "events": events,
        "stretched": stretched_rows[:40],
        "sympathy": sympathy,
        "data_ok": True,
        "notes": notes,
        "market_open": open_now,
        "as_of": datetime.now(tz=ET).isoformat(timespec="minutes"),
    }
    if now is None:
        _cache[key] = (time.time(), result)
    return result
