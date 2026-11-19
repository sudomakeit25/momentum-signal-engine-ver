"""Live record of the probability map: what it said for each tracked stock
after every session, scored once the sessions it was about have finished.

The walk-forward check in probability_map.py is scored on history that was
also used to choose the map's settings. This record is scored only on
sessions that had not happened when the odds were saved, so it is the
honest measure. A record uses only data up to its session's close, so it
can be saved any time before the next close: if the server sleeps through
an evening it catches up the next morning. A session it never saw is not
filled in afterwards.

Storage (Upstash Redis; in memory when Redis is not configured):
  mse:pmap:snap:v<N>:<date>  every tracked stock's table for that session,
                             odds in basis points; expires after SNAP_TTL
  mse:pmap:score:v<N>        running Brier totals per stock for method
                             version N, plus which sessions still have
                             windows to score
Each run is all or nothing: the totals and the "still to score" bookkeeping
live in the one score key and are written together at the end, so a run
that fails part way scores nothing and the retry starts clean. Windows are
measured in trading sessions on SPY's calendar, so a stock that was halted
for part of a window is scored the same way whenever the run happens.
Outcomes use the same split-adjusted series the odds came from, so a split
between saving and scoring does not skew them.
"""

from __future__ import annotations

import bisect
import json
import logging
import math
import time
from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np

from src.scanner import probability_map as pm

logger = logging.getLogger("mse.map_record")

ET = ZoneInfo("America/New_York")
FOCUS = ("CLSK", "RIOT", "MARA", "NVDA", "AVGO", "TSLA")
CHUNK = 20                       # stocks fetched per request, to keep memory flat
SNAP_TTL = 160 * 86400           # seconds a session's saved tables are kept
# A session counts as finished for the record from 16:25 New York time: the
# delayed feed has the closing prints by then. The background loop checks
# every 10 minutes, so the evening run lands about 16:25-16:40, inside the
# keep-alive (to 16:45). It may run any time except the busy start of the
# next session, so a server that slept through the evening still records
# the session the next morning or midday.
SESSION_FINAL = dtime(16, 25)
QUIET_FROM = dtime(9, 25)
QUIET_UNTIL = dtime(10, 15)
RETRY_EVERY = 30 * 60            # seconds to wait after a failed run
SESSION_DAYS = 100               # calendar days of SPY sessions used as the calendar
MIN_CALENDAR = 40                # fewer sessions than this from SPY is a data problem: try later
MISSING_OK = 5                   # saved stocks a fetch may lack (delisted) before the run is a data problem
MIN_DAYS_POOLED = 20             # scored sessions before a pooled verdict
MIN_DAYS_STOCK = 40              # scored sessions before a single stock's verdict
NEXT = "n"                       # the next-session 10% close, from the close and the open
KEYS = tuple(str(h) for h in pm.HORIZONS) + (NEXT,)
ROW_LEVELS = [lvl for lvl in reversed(pm.LEVELS)] + [-lvl for lvl in pm.LEVELS]   # as in the map's rows
NBINS = len(pm.BINS) - 1
_REPORT_TTL = 60

_mem: dict[str, str] = {}
_failed_at = 0.0
_done_for: str | None = None     # the last session this process has finished with
_report_cache: tuple[float, dict] | None = None


# ---------------------------------------------------------------- storage

def _redis():
    from src.data.redis_store import _get_redis
    return _get_redis()


def _get(key: str):
    """Stored value, or None. A Redis error is raised, so a run never works
    from a missing record and scores something twice."""
    r = _redis()
    raw = r.get(key) if r is not None else _mem.get(key)
    return json.loads(raw) if raw else None


def _set(key: str, value, ex: int | None = None) -> None:
    raw = json.dumps(value, separators=(",", ":"))
    r = _redis()
    if r is not None:
        r.set(key, raw, ex=ex)
    else:
        _mem[key] = raw


def snap_key(day: str, version: int | None = None) -> str:
    return f"mse:pmap:snap:v{pm.METHOD_VERSION if version is None else version}:{day}"


def score_key(version: int | None = None) -> str:
    return f"mse:pmap:score:v{pm.METHOD_VERSION if version is None else version}"


def _new_stock() -> dict:
    return {"h": {str(h): [0, 0.0, 0.0] for h in pm.HORIZONS},   # cells, Brier map, Brier usual
            "g10": [0, 0.0, 0.0],                                 # the +-10% rows only
            "bins": [[0, 0.0, 0.0] for _ in range(NBINS)],        # cells, sum said, sum happened
            "next": [0, 0.0, 0.0, 0],                             # cells, Brier map, Brier usual, 10% closes
            "open": [0, 0.0, 0.0]}                                # cells, Brier from the open, Brier usual


def _new_score() -> dict:
    # days: sessions scored per window; "o" counts sessions with odds from the open scored
    return {"version": pm.METHOD_VERSION, "since": None, "last_snap": None, "snapshots": 0,
            "days": {**{k: 0 for k in KEYS}, "o": 0}, "open": {}, "symbols": {}, "tracked": [],
            "updated": None}


# ---------------------------------------------------------------- inputs

def universe() -> list[str]:
    """The six stocks asked about, the intraday universe and the miners."""
    from src.scanner import intraday_movers as m
    from src.scanner.spike_reversal import EXTRA_GROUPS
    syms = list(FOCUS) + m._intraday_universe(None) + list(EXTRA_GROUPS["crypto_miners"])
    return [s for s in dict.fromkeys(syms) if "/" not in s]


def sessions(now_et: datetime) -> list[date]:
    """Finished trading sessions up to now (SPY's daily bars as the calendar);
    today's only from SESSION_FINAL."""
    from src.data import client
    spy = pm.clean_bars(client.get_multi_bars(["SPY"], days=SESSION_DAYS).get("SPY"))
    out = [d for d in spy.index if d <= now_et.date()]
    if out and out[-1] == now_et.date() and now_et.time() < SESSION_FINAL:
        out = out[:-1]
    return out


def _bp(x) -> int | None:
    return None if x is None else int(round(float(x) * 10000))


def record(d) -> dict | None:
    """One stock's table as the map shows it from the last row's close,
    compacted: odds and usual odds per row and window, in basis points."""
    out = pm.build(d, check=False)
    if not out.get("data_ok"):
        return None
    b = out["big_day"]
    return {"c": out["last_close"], "v": out["vol_pct"],
            "o": [[_bp(x) for x in r["odds"]] for r in out["rows"]],
            "u": [[_bp(x) for x in r["usual"]] for r in out["rows"]],
            "b": [_bp(b["up"]), _bp(b["down"]), _bp(b["usual_up"]), _bp(b["usual_down"])]}


# ---------------------------------------------------------------- scoring

def _bin(p: float) -> int:
    for i in range(NBINS):
        if pm.BINS[i] <= p < pm.BINS[i + 1]:
            return i
    return NBINS - 1


def score_one(st: dict, rec: dict, d, i: int, ends: dict[str, date]) -> list[str]:
    """Add one stock's saved forecast from row i of its bars d to its totals,
    for each window in `ends` (key -> the window's last session on the
    calendar). A window counts the stock's bars after row i up to that
    session; with no bars in it (halted throughout) it is not scored. The
    next-session close needs a bar on exactly that session. Returns the keys
    scored, plus "o" when the odds from the next open were scored too."""
    dates = list(d.index)
    c = d["close"].to_numpy(dtype=float)
    hi = d["high"].to_numpy(dtype=float)
    lo = d["low"].to_numpy(dtype=float)
    op = d["open"].to_numpy(dtype=float)
    done = []
    for k, end in ends.items():
        stop = bisect.bisect_right(dates, end)          # rows i+1 .. stop-1 are inside the window
        if stop <= i + 1:
            continue
        if k == NEXT:
            if dates[i + 1] != end:
                continue
            move = math.log(c[i + 1] / c[i])
            hits = [float(move >= math.log1p(pm.BIG_DAY_PCT / 100)),
                    float(move <= math.log1p(-pm.BIG_DAY_PCT / 100))]
            model = [rec["b"][0] / 1e4, rec["b"][1] / 1e4]
            usual = [rec["b"][2] / 1e4, rec["b"][3] / 1e4]
            n = st["next"]
            n[0] += 2
            n[1] += sum((m - h) ** 2 for m, h in zip(model, hits))
            n[2] += sum((u - h) ** 2 for u, h in zip(usual, hits))
            n[3] += int(sum(hits))
            # The panel's odds once the next session opened: same history, that open.
            if math.isfinite(op[i + 1]) and op[i + 1] > 0:
                oo = pm.open_odds_at(pm.prepare(d.iloc[: i + 1]), i, float(op[i + 1]))
                if oo:
                    o = st["open"]
                    o[0] += 2
                    o[1] += (oo["up"] - hits[0]) ** 2 + (oo["down"] - hits[1]) ** 2
                    o[2] += sum((u - h) ** 2 for u, h in zip(usual, hits))
                    done.append("o")
            done.append(k)
            continue
        j = pm.HORIZONS.index(int(k))
        up = math.log(float(np.max(hi[i + 1:stop])) / c[i])
        dn = math.log(float(np.min(lo[i + 1:stop])) / c[i])
        cell = st["h"][k]
        for r, lvl in enumerate(ROW_LEVELS):
            p, u = rec["o"][r][j], rec["u"][r][j]
            if p is None or u is None:
                continue
            p, u = p / 1e4, u / 1e4
            hit = float(up >= math.log1p(lvl / 100)) if lvl > 0 else float(dn <= math.log1p(lvl / 100))
            cell[0] += 1
            cell[1] += (p - hit) ** 2
            cell[2] += (u - hit) ** 2
            if abs(lvl) == pm.BIG_DAY_PCT:
                g = st["g10"]
                g[0] += 1
                g[1] += (p - hit) ** 2
                g[2] += (u - hit) ** 2
            b = st["bins"][_bin(p)]
            b[0] += 1
            b[1] += p
            b[2] += hit
        done.append(k)
    return done


def _ready(score: dict, cal: list[date]) -> dict[str, list[str]]:
    """Saved sessions with windows that have now finished: {date: keys}.
    Sessions older than the calendar are given up (dropped from `score`);
    one the calendar does not show (a gap, or a calendar that went back a
    session) waits for a later run."""
    pos = {str(d): i for i, d in enumerate(cal)}
    out = {}
    for day in list(score["open"]):
        if date.fromisoformat(day) < cal[0]:
            logger.info("Map record: gave up on %s windows from %s (older than the calendar)",
                        len(score["open"][day]), day)
            score["open"].pop(day)
            continue
        if day not in pos:
            continue
        after = len(cal) - 1 - pos[day]
        keys = [k for k in score["open"][day] if after >= (1 if k == NEXT else int(k))]
        if keys:
            out[day] = keys
    return out


def due(now: datetime | None = None) -> bool:
    """Not in the first part of the session, and not within RETRY_EVERY of a
    failed run. No I/O."""
    t = (now or datetime.now(ET)).astimezone(ET).time()
    return not (QUIET_FROM <= t < QUIET_UNTIL) and time.time() - _failed_at >= RETRY_EVERY


def needs_work(now: datetime | None = None) -> bool:
    """Whether a session has finished that this process has not finished
    with. One calendar read (SPY daily bars, cached on disk for a while);
    meant to run outside the heavy-step lock."""
    cal = sessions((now or datetime.now(ET)).astimezone(ET))
    return bool(cal) and _done_for != str(cal[-1])


def run_daily(now: datetime | None = None, symbols: list[str] | None = None) -> str | None:
    """Save the latest finished session's tables and score every saved
    session whose windows have finished. Returns a short summary, or None
    when there was nothing to do. Raises on data or storage errors, and when
    the data looks incomplete (a short calendar, or several saved stocks
    missing from the fetch): nothing is written then, and due() waits
    RETRY_EVERY before the next try."""
    global _failed_at
    try:
        return _run(now, symbols)
    except Exception:
        _failed_at = time.time()
        raise


def _run(now: datetime | None, symbols: list[str] | None) -> str | None:
    global _done_for, _report_cache, _failed_at
    now_et = (now or datetime.now(ET)).astimezone(ET)
    cal = sessions(now_et)
    if not cal:
        return None
    if len(cal) < MIN_CALENDAR:
        raise RuntimeError(f"only {len(cal)} sessions in the SPY calendar; trying later")
    as_of = cal[-1]
    if _done_for == str(as_of):
        return None
    score = _get(score_key()) or _new_score()
    last = score.get("last_snap")
    need_snap = last is None or as_of > date.fromisoformat(last)    # never back over a saved session
    todo = _ready(score, cal)
    if not need_snap and not todo:
        _done_for = str(as_of)
        return None
    saved = {}
    for day in todo:
        snap = _get(snap_key(day))
        if snap and snap.get("version") == pm.METHOD_VERSION:
            saved[day] = snap
        else:
            logger.warning("Map record: no saved tables for %s; its windows are dropped", day)
    pos_cal = {d: n for n, d in enumerate(cal)}
    ends = {day: {k: cal[pos_cal[date.fromisoformat(day)] + (1 if k == NEXT else int(k))] for k in keys}
            for day, keys in todo.items()}
    # Stocks saved earlier are scored even if they have since left the universe.
    syms = list(dict.fromkeys((symbols or universe()) + [s for snap in saved.values() for s in snap["symbols"]]))
    from src.data import client
    new, no_table, unscored, scored = {}, 0, 0, 0
    opened: set[str] = set()
    missing = set()                                 # saved stocks the fetch had no bar for on their day
    for start in range(0, len(syms), CHUNK):
        chunk = syms[start:start + CHUNK]
        bars = client.get_multi_bars(chunk, days=pm.HISTORY_DAYS)
        for sym in chunk:
            d = pm.clean_bars(bars.get(sym))
            d = d[[x <= as_of for x in d.index]] if not d.empty else d
            if need_snap:
                rec = record(d) if len(d) and d.index[-1] == as_of else None
                if rec:
                    new[sym] = rec
                else:
                    no_table += 1
            pos = {x: n for n, x in enumerate(d.index)}
            for day, keys in todo.items():
                rec = (saved.get(day) or {}).get("symbols", {}).get(sym)
                if rec is None:
                    continue                                # not saved for this stock that day
                i = pos.get(date.fromisoformat(day))
                got = []
                if i is None:
                    missing.add(sym)
                else:
                    st = score["symbols"].setdefault(sym, _new_stock())
                    got = score_one(st, rec, d, i, {k: ends[day][k] for k in keys})
                    if "o" in got:
                        opened.add(day)
                        got.remove("o")
                scored += len(got)
                unscored += len(keys) - len(got)
        del bars
    if len(missing) > MISSING_OK:
        raise RuntimeError(f"{len(missing)} saved stocks came back without bars ({', '.join(sorted(missing)[:8])}"
                           f"{', ...' if len(missing) > 8 else ''}); trying later")
    for day, keys in todo.items():
        for k in keys:
            if day in saved:
                score["days"][k] += 1
            score["open"][day].remove(k)
        if day in opened:
            score["days"]["o"] = score["days"].get("o", 0) + 1
        if not score["open"][day]:
            score["open"].pop(day)
            if _redis() is None:
                _mem.pop(snap_key(day), None)               # memory only: nothing expires it
    if need_snap and new:
        _set(snap_key(str(as_of)), {"as_of": str(as_of), "version": pm.METHOD_VERSION,
                                    "taken_at": now_et.isoformat(timespec="minutes"), "symbols": new},
             ex=SNAP_TTL)
        score["open"].setdefault(str(as_of), list(KEYS))
        score["tracked"] = sorted(new)
        score["last_snap"] = str(as_of)
        score["snapshots"] += 1
        score["since"] = score["since"] or str(as_of)
    score["updated"] = now_et.isoformat(timespec="minutes")
    _set(score_key(), score)
    _report_cache = None
    if not need_snap or new:
        _done_for = str(as_of)
    else:
        # The calendar has the session but no stock had a bar for it: try
        # again after RETRY_EVERY rather than refetching every loop.
        _failed_at = time.time()
        logger.warning("Map record: no stock had a bar for %s yet; trying again later", as_of)
    if missing:
        logger.info("Map record: %d saved stocks came back without bars: %s", len(missing),
                    ", ".join(sorted(missing)))
    if unscored:
        logger.info("Map record: %d stock windows could not be scored (no bars in the window, "
                    "or no bar on the session itself)", unscored)
    parts = [f"saved {len(new)} stocks for {as_of}" + (f" ({no_table} without a table)" if no_table else "")
             if need_snap else f"{as_of} already saved"]
    parts.append(f"scored {scored} stock windows from {len(todo)} earlier sessions"
                 + (f", {unscored} could not be scored" if unscored else ""))
    return "; ".join(parts)


# ---------------------------------------------------------------- reading

def _skill(m: float, u: float) -> float | None:
    return None if not u else 1 - m / u


def _sum(stocks: list[dict]) -> dict:
    tot = _new_stock()
    for st in stocks:
        for k in tot["h"]:
            tot["h"][k] = [a + b for a, b in zip(tot["h"][k], st["h"][k])]
        tot["g10"] = [a + b for a, b in zip(tot["g10"], st["g10"])]
        tot["bins"] = [[a + b for a, b in zip(x, y)] for x, y in zip(tot["bins"], st["bins"])]
        tot["next"] = [a + b for a, b in zip(tot["next"], st["next"])]
        tot["open"] = [a + b for a, b in zip(tot["open"], st["open"])]
    return tot


def summarize(st: dict, min_days: int, days: dict | None = None) -> dict:
    """Skills, verdicts and counts for one stock's totals (or a pooled sum).
    `days` are the sessions scored per window; for one stock they come from
    its own cell counts."""
    rows = len(ROW_LEVELS)
    if days is None:
        days = {k: st["h"][k][0] // rows for k in st["h"]}
        days[NEXT] = st["next"][0] // 2
        days["o"] = st["open"][0] // 2
    grid_n = sum(st["h"][k][0] for k in st["h"])
    bm = sum(st["h"][k][1] for k in st["h"])
    bu = sum(st["h"][k][2] for k in st["h"])
    skill = _skill(bm, bu) if grid_n else None
    enough = days.get("1", 0) >= min_days
    nxt, opn = st["next"], st["open"]
    next_enough = days.get(NEXT, 0) >= min_days
    return {
        "days": days, "cells": grid_n,
        "skill": skill, "skill_10": _skill(st["g10"][1], st["g10"][2]) if st["g10"][0] else None,
        "verdict": pm.verdict(skill) if enough else None,
        "by_window": [{"sessions": int(k), "days": days.get(k, 0), "cells": st["h"][k][0],
                       "skill": _skill(st["h"][k][1], st["h"][k][2]) if st["h"][k][0] else None}
                      for k in st["h"]],
        "bins": [{"lo": pm.BINS[i], "hi": min(pm.BINS[i + 1], 1.0), "n": b[0],
                  "said": b[1] / b[0], "happened": b[2] / b[0]} for i, b in enumerate(st["bins"]) if b[0]],
        "next": {"days": days.get(NEXT, 0), "open_days": days.get("o", 0), "happened": nxt[3],
                 "skill": _skill(nxt[1], nxt[2]) if nxt[0] else None,
                 "verdict": pm.verdict(_skill(nxt[1], nxt[2])) if nxt[0] and next_enough else None,
                 "open_skill": _skill(opn[1], opn[2]) if opn[0] else None,
                 "open_verdict": pm.verdict(_skill(opn[1], opn[2])) if opn[0] and next_enough else None},
        "min_days": min_days,
    }


def live_for(symbol: str) -> dict | None:
    """One stock's live record for its panel, or None before anything is
    saved. Never raises."""
    try:
        score = _get(score_key())
    except Exception as e:
        logger.warning("Map record read failed: %s", str(e)[:120])
        return None
    if not score or not score.get("since"):
        return None
    sym = symbol.upper()
    st = score["symbols"].get(sym)
    if st is None and sym in score.get("tracked", []):
        st = _new_stock()                           # saved, nothing scored yet
    out = {"since": score["since"], "last_saved": score["last_snap"]}
    return {**out, **summarize(st, MIN_DAYS_STOCK)} if st else {**out, "days": None}


def report() -> dict:
    """The pooled record for the Scorecard page. Never raises."""
    global _report_cache
    if _report_cache and time.time() - _report_cache[0] < _REPORT_TTL:
        return _report_cache[1]
    try:
        score = _get(score_key())
    except Exception as e:
        logger.warning("Map record read failed: %s", str(e)[:120])
        return {"ok": False, "note": "Could not read the record right now."}
    if not score or not score.get("since"):
        out = {"ok": True, "since": None, "note": "Nothing recorded yet: the first tables are saved "
                                                  "after the next close."}
    else:
        stocks = score["symbols"]
        pooled = summarize(_sum(list(stocks.values())), MIN_DAYS_POOLED, dict(score["days"]))
        out = {"ok": True, "since": score["since"], "last_saved": score["last_snap"],
               "sessions_saved": score["snapshots"], "stocks": len(stocks), "updated": score["updated"],
               "waiting": sorted(score["open"]),
               "pooled": pooled,
               "focus": [{"symbol": s, **summarize(stocks[s], MIN_DAYS_STOCK)} for s in FOCUS if s in stocks]}
    _report_cache = (time.time(), out)
    return out
