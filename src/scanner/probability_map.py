"""Probability map: how often a stock has reached the levels around its
price, scaled to how much it is moving now.

For every past session, the method records how far the stock went over the
next 1, 5, 10 and 20 sessions (highest high, lowest low, close), measured in
units of its daily volatility on that day. The odds for a level today are
the share of past sessions whose move, in those units, would have reached
it at today's volatility ("filtered historical simulation"). That keeps the
stock's own fat tails and lopsidedness, and widens the odds when it is
moving a lot and narrows them when it is quiet.

Once today's open is known, the next-session 10% odds are redone from the
opening gap: the share of past sessions whose open-to-close move (in units
of volatility, from sessions with a similar gap) would carry today's open to
10% from the previous close.

Every map carries a walk-forward check: the same method run on each of the
last CAL_SESSIONS sessions using only what was known then, scored (Brier)
against what happened and against the stock's usual, unscaled odds.

Describes past frequencies. It knows nothing about news or earnings and
does not forecast direction. The volatility settings were picked with the
same kind of check (scripts/probability_map_check.py, 170 stocks), so the
check flatters the map slightly; the margin between settings was small.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

logger = logging.getLogger("mse.probability_map")

ET = ZoneInfo("America/New_York")
# Raise when the method or its settings change, so the live record
# (src/scanner/map_record.py) scores each version separately.
METHOD_VERSION = 1
LEVELS = (5.0, 10.0, 20.0, 30.0)         # percent from the last close, both ways
HORIZONS = (1, 5, 10, 20)                # sessions
BIG_DAY_PCT = 10.0
# Volatility is half a short-term estimate and half a long-term one, so it
# reacts to a burst of moves but drifts back toward the stock's usual level.
# Chosen by scripts/probability_map_check.py over 170 stocks: this blend
# scored best at every horizon (10 alone, 40, 80 and 160 sessions alone,
# range-based and a flat 250-session window were all worse).
SHORT_HALFLIFE = 10     # sessions: a day's move counts half as much 10 sessions later
LONG_HALFLIFE = 160
SHORT_WEIGHT = 0.5
WARMUP = 20             # daily returns needed before a volatility is used
VOL_FLOOR = 0.002       # 0.2% a day, so a flat stretch cannot divide by almost nothing
HISTORY_DAYS = 2200     # calendar days fetched, about six years
MIN_ORIGINS = 250       # past sessions with known outcomes needed before giving odds
CAL_SESSIONS = 500      # sessions in the walk-forward check
MIN_CAL = 100           # fewer checked sessions than this: no verdict
BINS = (0.0, 0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 1.0001)
SKILL_MARGIN = 0.02
_TTL = 10 * 60
_CACHE_MAX = 64         # served by a public endpoint, so the cache is bounded
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()   # the route runs in a thread pool
# One map is built at a time: a build is a few hundred milliseconds of CPU on
# a public endpoint, and requests for the same stock that arrive together then
# share one build instead of each fetching.
_build_slot = threading.BoundedSemaphore(1)
BUILD_WAIT = 30         # seconds a request waits for the build slot
SESSION_OPEN = dtime(9, 30)
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


# ---------------------------------------------------------------- inputs

def clean_bars(df: pd.DataFrame | None) -> pd.DataFrame:
    """Daily bars, one row per date, oldest first. Highs and lows are made to
    contain the close; missing or bad opens stay NaN."""
    from src.scanner.recent_performance import _clean
    d = _clean(df)
    if d.empty:
        return d
    c = d["close"]
    d["high"] = np.fmax(d["high"].where(d["high"] > 0), c)
    d["low"] = np.fmin(d["low"].where(d["low"] > 0), c)
    d["open"] = d["open"].where(d["open"] > 0)
    return d


def daily_vol(close, short: float = SHORT_HALFLIFE, long: float = LONG_HALFLIFE,
              weight: float = SHORT_WEIGHT) -> np.ndarray:
    """Daily volatility at each session from log returns up to and including
    it: a blend of a short and a long exponentially weighted variance (zero
    mean). NaN for the first WARMUP sessions."""
    c = np.asarray(close, dtype=float)
    if c.size == 0:
        return c
    r2 = pd.Series(np.r_[np.nan, np.diff(np.log(c))] ** 2)
    var = (weight * r2.ewm(halflife=short, min_periods=WARMUP).mean()
           + (1 - weight) * r2.ewm(halflife=long, min_periods=WARMUP).mean()).to_numpy()
    sig = np.sqrt(var)
    return np.where(np.isfinite(sig), np.maximum(sig, VOL_FLOOR), np.nan)


def forward_moves(d: pd.DataFrame, h: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Log move from each session's close to the highest high, the lowest low
    and the close of the next h sessions. NaN where those are not in the data."""
    c = d["close"].to_numpy(dtype=float)
    hi = d["high"].reset_index(drop=True).rolling(h).max().shift(-h).to_numpy(dtype=float)
    lo = d["low"].reset_index(drop=True).rolling(h).min().shift(-h).to_numpy(dtype=float)
    cl = np.r_[c[h:], np.full(min(h, c.size), np.nan)][: c.size]
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(hi / c), np.log(lo / c), np.log(cl / c)


def prepare(d: pd.DataFrame) -> dict:
    """Everything the odds are computed from, indexed by the origin session."""
    c = d["close"].to_numpy(dtype=float)
    o = d["open"].to_numpy(dtype=float)
    sig = daily_vol(c)
    z = {}
    for h in HORIZONS:
        up, dn, cl = forward_moves(d, h)
        with np.errstate(invalid="ignore"):
            z[h] = {"up": up, "dn": dn, "cl": cl, "zup": up / sig, "zdn": dn / sig, "zcl": cl / sig}
    with np.errstate(divide="ignore", invalid="ignore"):
        gap = np.r_[np.log(o[1:] / c[:-1]), np.nan] if c.size else c       # next session's opening gap
        oc = np.r_[np.log(c[1:] / o[1:]), np.nan] if c.size else c         # and its open-to-close move
    valid = np.flatnonzero(np.isfinite(sig))
    return {"dates": list(d.index), "close": c, "sig": sig, "z": z, "gap": gap, "oc": oc,
            "zgap": gap / sig, "zoc": oc / sig, "first": int(valid[0]) if valid.size else None}


# ---------------------------------------------------------------- odds

def _share(sample: np.ndarray, thresholds, below: bool = False) -> tuple[np.ndarray, int]:
    s = sample[np.isfinite(sample)]
    thr = np.atleast_1d(np.asarray(thresholds, dtype=float))
    if s.size == 0:
        return np.full(thr.shape, np.nan), 0
    hit = (s[:, None] <= thr[None, :]) if below else (s[:, None] >= thr[None, :])
    return hit.mean(axis=0), int(s.size)


_UP = np.log1p(np.asarray(LEVELS) / 100)
_DN = np.log1p(-np.asarray(LEVELS) / 100)
_BIG_UP = math.log1p(BIG_DAY_PCT / 100)
_BIG_DN = math.log1p(-BIG_DAY_PCT / 100)


def grid_at(p: dict, t: int) -> dict | None:
    """Odds of trading at or beyond each level within each horizon, from the
    close of session t, using only sessions whose outcomes were all known
    by then (s <= t - max horizon), so a longer window never shows lower odds.
    Returns {"up","dn","usual_up","usual_dn": arrays [horizon][level], "cases"}."""
    end = t - max(HORIZONS) + 1
    sig_t = p["sig"][t] if 0 <= t < len(p["sig"]) else np.nan
    if end <= 0 or not np.isfinite(sig_t):
        return None
    out = {k: np.full((len(HORIZONS), len(LEVELS)), np.nan) for k in ("up", "dn", "usual_up", "usual_dn")}
    cases = 0
    ok = np.isfinite(p["sig"][:end])
    for i, h in enumerate(HORIZONS):
        z = p["z"][h]
        out["up"][i], cases = _share(z["zup"][:end][ok], _UP / sig_t)
        out["dn"][i], _ = _share(z["zdn"][:end][ok], _DN / sig_t, below=True)
        out["usual_up"][i], _ = _share(z["up"][:end][ok], _UP)
        out["usual_dn"][i], _ = _share(z["dn"][:end][ok], _DN, below=True)
    if cases < MIN_ORIGINS:
        return None
    out["cases"] = cases
    return out


def big_day_at(p: dict, t: int) -> dict | None:
    """Odds the session after t closes BIG_DAY_PCT or more up or down from
    t's close, from the sessions before t."""
    sig_t = p["sig"][t] if 0 <= t < len(p["sig"]) else np.nan
    if t <= 0 or not np.isfinite(sig_t):
        return None
    z = p["z"][1]
    ok = np.isfinite(p["sig"][:t])
    up, cases = _share(z["zcl"][:t][ok], [_BIG_UP / sig_t])
    dn, _ = _share(z["zcl"][:t][ok], [_BIG_DN / sig_t], below=True)
    usual_up, _ = _share(z["cl"][:t][ok], [_BIG_UP])
    usual_dn, _ = _share(z["cl"][:t][ok], [_BIG_DN], below=True)
    if cases < MIN_ORIGINS:
        return None
    return {"up": float(up[0]), "down": float(dn[0]), "usual_up": float(usual_up[0]),
            "usual_down": float(usual_dn[0]), "cases": cases}


def open_odds_at(p: dict, t: int, open_price: float) -> dict | None:
    """Odds the session after t closes BIG_DAY_PCT up or down from t's close,
    once that session's open is known: the share of earlier sessions whose
    open-to-close move, in units of volatility, would get there from this
    open. (Matching only sessions with a similar gap made no difference
    across 170 stocks, so all are used.)"""
    sig_t = p["sig"][t] if 0 <= t < len(p["sig"]) else np.nan
    try:
        price = float(open_price)
    except (TypeError, ValueError):
        return None
    if t <= 0 or not np.isfinite(sig_t) or not math.isfinite(price) or price <= 0:
        return None
    g = math.log(price / p["close"][t])
    zg, zoc = p["zgap"][:t], p["zoc"][:t]
    ok = np.isfinite(zg) & np.isfinite(zoc)
    zg, zoc = zg[ok], zoc[ok]
    if zg.size < MIN_ORIGINS:
        return None
    up, cases = _share(zoc, [(_BIG_UP - g) / sig_t])
    dn, _ = _share(zoc, [(_BIG_DN - g) / sig_t], below=True)
    return {"up": float(up[0]), "down": float(dn[0]), "gap_pct": (math.exp(g) - 1) * 100, "cases": cases}


# ---------------------------------------------------------------- walk-forward check

def _bins(pred: np.ndarray, hit: np.ndarray) -> list[dict]:
    out = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        m = (pred >= lo) & (pred < hi)
        if m.any():
            out.append({"lo": lo, "hi": min(hi, 1.0), "n": int(m.sum()),
                        "said": float(pred[m].mean()), "happened": float(hit[m].mean())})
    return out


def _skill(model: float, usual: float) -> float | None:
    return None if not usual else 1 - model / usual


def calibrate(p: dict, sessions: int = CAL_SESSIONS) -> dict | None:
    """Run the map on each of the last `sessions` sessions whose outcomes are
    known, using only what was known at each, and score it. Brier scores are
    returned as sums with counts so several stocks can be pooled."""
    n, first = len(p["close"]), p["first"]
    if first is None:
        return None
    hmax = max(HORIZONS)
    t_hi = n - 1 - hmax
    t_lo = max(first + MIN_ORIGINS + hmax - 1, t_hi - sessions + 1)
    pm, pu, hit, ten = [], [], [], []
    is10 = np.array([lvl == BIG_DAY_PCT for lvl in LEVELS])
    for t in range(t_lo, t_hi + 1):
        g = grid_at(p, t)
        if g is None:
            continue
        for i, h in enumerate(HORIZONS):
            z = p["z"][h]
            pm += [g["up"][i], g["dn"][i]]
            pu += [g["usual_up"][i], g["usual_dn"][i]]
            hit += [z["up"][t] >= _UP, z["dn"][t] <= _DN]
            ten += [is10, is10]
    grid = None
    if pm:
        pm, pu = np.concatenate(pm), np.concatenate(pu)
        hit, ten = np.concatenate(hit).astype(float), np.concatenate(ten)
        tested = len(pm) // (2 * len(HORIZONS) * len(LEVELS))
        grid = {"sessions": tested, "count": int(pm.size),
                "brier_model": float(((pm - hit) ** 2).sum()), "brier_usual": float(((pu - hit) ** 2).sum()),
                "brier_model_10": float(((pm[ten] - hit[ten]) ** 2).sum()),
                "brier_usual_10": float(((pu[ten] - hit[ten]) ** 2).sum()), "count_10": int(ten.sum()),
                "bins": _bins(pm, hit), "from": str(p["dates"][max(t_lo, t_hi - tested + 1)]),
                "to": str(p["dates"][t_hi])}

    # Next-session 10% closes: from the close, and from the next open.
    b_lo = max(first + MIN_ORIGINS, n - 1 - sessions)
    bm, bu, bo, bh = [], [], [], []
    b_first = b_last = None
    for t in range(b_lo, n - 1):
        b = big_day_at(p, t)
        if b is None:
            continue
        b_first = t if b_first is None else b_first
        b_last = t
        cl = p["z"][1]["cl"][t]
        h_up, h_dn = float(cl >= _BIG_UP), float(cl <= _BIG_DN)
        bm += [b["up"], b["down"]]
        bu += [b["usual_up"], b["usual_down"]]
        bh += [h_up, h_dn]
        nxt_open = p["close"][t] * math.exp(p["gap"][t]) if np.isfinite(p["gap"][t]) else None
        oo = open_odds_at(p, t, nxt_open) if nxt_open else None
        bo += [oo["up"], oo["down"]] if oo else [np.nan, np.nan]
    big = None
    if bm:
        bm, bu, bo, bh = (np.asarray(x, dtype=float) for x in (bm, bu, bo, bh))
        has = np.isfinite(bo)
        big = {"sessions": len(bm) // 2, "count": int(bm.size),
               "brier_model": float(((bm - bh) ** 2).sum()), "brier_usual": float(((bu - bh) ** 2).sum()),
               "count_open": int(has.sum()),
               "brier_open": float(((bo[has] - bh[has]) ** 2).sum()),
               "brier_usual_open": float(((bu[has] - bh[has]) ** 2).sum()),
               "happened": int(bh.sum()),
               # the sessions whose closes were scored
               "from": str(p["dates"][b_first + 1]), "to": str(p["dates"][b_last + 1])}
    if grid is None and big is None:
        return None
    return {"grid": grid, "big_day": big}


def verdict(skill: float | None) -> str | None:
    if skill is None:
        return None
    if skill >= SKILL_MARGIN:
        return "more accurate than its usual odds"
    if skill > -SKILL_MARGIN:
        return "about as accurate as its usual odds"
    return "less accurate than its usual odds"


def _summary(cal: dict | None) -> dict | None:
    """The check as shown on the page: skills, verdicts and reliability bins."""
    if not cal:
        return None
    g, b = cal.get("grid"), cal.get("big_day")
    out: dict = {"sessions": 0}
    if g and g["sessions"] >= MIN_CAL:
        skill = _skill(g["brier_model"], g["brier_usual"])
        out.update({"sessions": g["sessions"], "from": g["from"], "to": g["to"],
                    "skill": skill, "skill_10": _skill(g["brier_model_10"], g["brier_usual_10"]),
                    "verdict": verdict(skill), "bins": g["bins"]})
    if b and b["sessions"] >= MIN_CAL:
        bs = _skill(b["brier_model"], b["brier_usual"])
        os_ = _skill(b["brier_open"], b["brier_usual_open"]) if b["count_open"] else None
        out["big_day"] = {"sessions": b["sessions"], "happened": b["happened"], "from": b["from"], "to": b["to"],
                          "skill": bs, "verdict": verdict(bs),
                          "open_skill": os_, "open_verdict": verdict(os_)}
    return out if out["sessions"] or "big_day" in out else None


# ---------------------------------------------------------------- assembly

def _r(v, n=4):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, n) if math.isfinite(f) else None


def build(d: pd.DataFrame, today_open: float | None = None, today: date | None = None,
          check: bool = True) -> dict:
    """The map from cleaned daily bars whose last row is the last finished
    session. `today_open` is the open of the session in progress, if any."""
    d = clean_bars(d)
    need = WARMUP + MIN_ORIGINS + max(HORIZONS) + 1
    if len(d) < need:
        return {"data_ok": False,
                "note": f"Only {len(d)} sessions of history; the map needs at least {need}."}
    p = prepare(d)
    t = len(d) - 1
    g = grid_at(p, t)
    big = big_day_at(p, t)
    if g is None or big is None:
        return {"data_ok": False, "note": "Not enough usable history for this stock."}
    close = float(p["close"][t])
    rows = []
    for j in reversed(range(len(LEVELS))):
        lvl = LEVELS[j]
        rows.append({"level_pct": lvl, "price": _r(close * (1 + lvl / 100), 4),
                     "odds": [_r(g["up"][i][j]) for i in range(len(HORIZONS))],
                     "usual": [_r(g["usual_up"][i][j]) for i in range(len(HORIZONS))]})
    for j in range(len(LEVELS)):
        lvl = LEVELS[j]
        rows.append({"level_pct": -lvl, "price": _r(close * (1 - lvl / 100), 4),
                     "odds": [_r(g["dn"][i][j]) for i in range(len(HORIZONS))],
                     "usual": [_r(g["usual_dn"][i][j]) for i in range(len(HORIZONS))]})
    sig_hist = p["sig"][np.isfinite(p["sig"])]
    out = {
        "data_ok": True, "note": None,
        "as_of": str(p["dates"][t]), "last_close": _r(close, 4),
        "history_sessions": g["cases"],
        "history_from": str(p["dates"][p["first"]]),
        "vol_pct": _r(p["sig"][t] * 100, 3),
        "vol_usual_pct": _r(float(np.median(sig_hist)) * 100, 3),
        "levels": list(LEVELS), "horizons": list(HORIZONS),
        "rows": rows,
        "big_day": {"level_pct": BIG_DAY_PCT, **{k: _r(v) for k, v in big.items() if k != "cases"},
                    "cases": big["cases"]},
        "today": None,
        "calibration": None,
    }
    if today_open is not None:
        oo = open_odds_at(p, t, today_open)
        if oo:
            out["today"] = {"date": str(today) if today else None, "open": _r(today_open, 4),
                            "gap_pct": _r(oo["gap_pct"], 3), "up": _r(oo["up"]), "down": _r(oo["down"]),
                            "cases": oo["cases"]}
    if check:
        out["calibration"] = _summary(calibrate(p))
    return out


def _sessions_until(last: date, when: str) -> int | None:
    try:
        return int(np.busday_count(last, date.fromisoformat(when[:10])))
    except (ValueError, TypeError):
        return None


def _cache_get(sym: str) -> dict | None:
    with _cache_lock:
        hit = _cache.get(sym)
    return hit[1] if hit and time.time() - hit[0] < _TTL else None


def _cache_put(sym: str, out: dict) -> None:
    with _cache_lock:
        if sym not in _cache and len(_cache) >= _CACHE_MAX:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]), None)
        _cache[sym] = (time.time(), out)


def probability_map(symbol: str, now: datetime | None = None) -> dict:
    """The map for one symbol. Never raises: data_ok False with a note when
    it cannot be built."""
    sym = (symbol or "").strip().upper()
    base = {"symbol": sym, "data_ok": False}
    if not _SYMBOL.match(sym):
        return {**base, "note": "Not a stock symbol."}
    hit = _cache_get(sym)
    if hit is not None:
        return hit
    if not _build_slot.acquire(timeout=BUILD_WAIT):
        return {**base, "note": "Busy building other maps; try again in a moment."}
    try:
        hit = _cache_get(sym)               # built while this request waited
        return hit if hit is not None else _build_symbol(sym, base, now)
    finally:
        _build_slot.release()


def _build_symbol(sym: str, base: dict, now: datetime | None) -> dict:
    try:
        from src.data import client
        from src.scanner.recent_performance import _in_progress
        d = clean_bars(client.get_multi_bars([sym], days=HISTORY_DAYS).get(sym))
        if d.empty:
            out = {**base, "note": f"No price history for {sym}."}
        else:
            now_et = (now or datetime.now(ET)).astimezone(ET)
            today_open, in_progress = None, _in_progress(d.index[-1], now_et)
            if in_progress:
                row = d.iloc[-1]
                o = float(row["open"]) if pd.notna(row["open"]) else None
                # Only a regular-session open inside the session's own range is used.
                if o is not None and now_et.time() >= SESSION_OPEN and row["low"] <= o <= row["high"]:
                    today_open = o
                d = d.iloc[:-1]
            out = {"symbol": sym, **build(d, today_open, now_et.date() if in_progress else None),
                   "in_progress": in_progress}
            if out["data_ok"]:
                out["earnings"] = _earnings(sym, date.fromisoformat(out["as_of"]))
                out["live"] = _live(sym)
    except Exception as e:
        logger.warning("Probability map failed for %s: %s", sym, str(e)[:160])
        return {**base, "note": "Could not build the map right now."}     # not cached: retried next time
    _cache_put(sym, out)
    return out


def _live(sym: str) -> dict | None:
    """The stock's live record (forecasts saved daily and scored later)."""
    try:
        from src.scanner import map_record
        return map_record.live_for(sym)
    except Exception as e:
        logger.warning("Map record lookup failed for %s: %s", sym, str(e)[:120])
        return None


def _earnings(sym: str, last: date) -> dict:
    """Next earnings date, if the data plan covers the stock: the map does
    not single out earnings days, so the page says when one falls inside it."""
    try:
        from src.data import fmp_client
        known, when = fmp_client.get_symbol_next_earnings(sym)
    except Exception:
        known, when = False, None
    return {"known": bool(known), "date": when,
            "sessions_away": _sessions_until(last, when) if when else None}
