"""Scorecard: did the alerts work?

Every detection (intraday setups, forming-setup watches, intraday patterns,
spikes, reversals) is logged once per symbol, kind and day with the price at
the time. Later the price is looked up at fixed horizons:

    15 minutes, 1 hour, that day's close, 1 session later, 5 sessions later

Returns are signed by the alert's direction, so a positive number always
means the alert was right. For setups that carried a stop and a target, the
scorecard also records which was touched first that day.

Nothing here predicts anything. It is the measurement that says which
detectors deserve attention, alerts, or automation.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src.data import client
from src.data.redis_store import _get_redis

logger = logging.getLogger("mse.scorecard")

ET = ZoneInfo("America/New_York")
_KEY = "mse:scorecard"
_MAX_RECORDS = 4000
_KEEP_DAYS = 90
HORIZONS = ("m15", "h1", "eod", "d1", "d5")

_lock = threading.RLock()
_mem: list[dict] | None = None      # in-process copy; the store when Redis is absent
_last_refresh = 0.0


# -------------------------------------------------------------------- store

def _load() -> list[dict]:
    global _mem
    with _lock:
        redis = _get_redis()
        if redis is not None:
            try:
                raw = redis.get(_KEY)
                data = json.loads(raw) if isinstance(raw, str) else (raw or [])
                if isinstance(data, list):
                    _mem = data
            except Exception as e:
                logger.warning("Scorecard read failed: %s", str(e)[:120])
        return list(_mem or [])


def _save(records: list[dict]) -> None:
    global _mem
    with _lock:
        cutoff = (datetime.now(tz=ET).date() - timedelta(days=_KEEP_DAYS)).isoformat()
        records = [r for r in records if r.get("date", "") >= cutoff][-_MAX_RECORDS:]
        _mem = records
        redis = _get_redis()
        if redis is not None:
            try:
                redis.set(_KEY, json.dumps(records))
            except Exception as e:
                logger.warning("Scorecard write failed: %s", str(e)[:120])


# ------------------------------------------------------------------ logging

def log_alerts(alerts: list[dict], now: datetime | None = None) -> int:
    """Record alerts not yet recorded today. Each alert needs symbol, kind,
    direction ("up"/"down") and price; stop, target and time are optional.
    Returns how many were new."""
    usable = [
        a for a in alerts
        if a.get("symbol") and a.get("kind") and a.get("direction") in ("up", "down")
        and isinstance(a.get("price"), (int, float)) and a["price"] > 0
    ]
    if not usable:
        return 0
    stamp = (now or datetime.now(tz=ET)).astimezone(ET)
    with _lock:
        records = _load()
        seen = {r["id"] for r in records}
        added = 0
        for a in usable:
            ts = a.get("time") or stamp.isoformat(timespec="seconds")
            try:
                when = datetime.fromisoformat(str(ts))
                when = when.replace(tzinfo=ET) if when.tzinfo is None else when.astimezone(ET)
            except ValueError:
                when = stamp
            day = when.date().isoformat()
            rid = f"{day}:{a['symbol']}:{a['kind']}:{a['direction']}"
            if rid in seen:
                continue
            seen.add(rid)
            records.append({
                "id": rid, "ts": when.isoformat(timespec="seconds"), "date": day,
                "symbol": a["symbol"], "kind": a["kind"], "direction": a["direction"],
                "price": round(float(a["price"]), 4),
                "stop": a.get("stop"), "target": a.get("target"),
                "outcome": {}, "final": False,
            })
            added += 1
        if added:
            _save(records)
        return added


def from_signal(s) -> dict:
    """A Signal (entry / stop / target) as a scorecard alert."""
    return {
        "symbol": s.symbol, "kind": s.setup_type.value,
        "direction": "up" if s.action.value == "BUY" else "down",
        "price": s.entry, "stop": s.stop_loss, "target": s.target,
        "time": s.timestamp.isoformat() if getattr(s, "timestamp", None) else None,
    }


# --------------------------------------------------------------- evaluation

def _signed(price: float, entry: float, direction: str) -> float:
    move = (price / entry - 1) * 100
    return round(move if direction == "up" else -move, 2)


def _to_et(df: pd.DataFrame) -> pd.DataFrame:
    idx = pd.to_datetime(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    out = df.copy()
    out.index = idx.tz_convert(ET)
    return out.sort_index()


def evaluate(record: dict, bars5: pd.DataFrame | None, daily: pd.DataFrame | None,
             today: date) -> dict:
    """Fill in whatever horizons the data now allows. Pure: returns a new
    outcome dict and does not touch the record."""
    out = dict(record.get("outcome") or {})
    entry, direction = float(record["price"]), record["direction"]
    when = datetime.fromisoformat(record["ts"])
    day = when.date()

    if bars5 is not None and not bars5.empty:
        b = _to_et(bars5)
        same = b[(b.index.date == day) & (b.index > when)]
        if not same.empty:
            for name, minutes in (("m15", 15), ("h1", 60)):
                if name not in out:
                    at = same[same.index >= when + timedelta(minutes=minutes)]
                    if not at.empty:
                        out[name] = _signed(float(at["close"].iloc[0]), entry, direction)
            stop, target = record.get("stop"), record.get("target")
            if stop and target and "first_touch" not in out and day < today:
                out["first_touch"] = _first_touch(same, float(stop), float(target), direction)

    if daily is not None and not daily.empty:
        d = daily.sort_index()
        idx = pd.to_datetime(d.index)
        if idx.tz is not None:
            idx = idx.tz_convert("UTC")
        days = [ts.date() for ts in idx]
        closes = d["close"].astype(float).tolist()
        if day in days:
            i = days.index(day)
            if day < today and "eod" not in out:
                out["eod"] = _signed(closes[i], entry, direction)
            for name, n in (("d1", 1), ("d5", 5)):
                j = i + n
                # a session only counts once it has closed
                if name not in out and j < len(closes) and days[j] < today:
                    out[name] = _signed(closes[j], entry, direction)
    return out


def _first_touch(bars: pd.DataFrame, stop: float, target: float, direction: str) -> str:
    for _, bar in bars.iterrows():
        hi, lo = float(bar["high"]), float(bar["low"])
        hit_target = hi >= target if direction == "up" else lo <= target
        hit_stop = lo <= stop if direction == "up" else hi >= stop
        if hit_target and hit_stop:
            return "stop"          # both inside one bar: assume the worse
        if hit_stop:
            return "stop"
        if hit_target:
            return "target"
    return "neither"


def refresh_outcomes(now: datetime | None = None, min_interval: float = 300.0) -> int:
    """Look up prices for records that are not final. Returns how many
    records changed. Throttled, since it fetches bars."""
    global _last_refresh
    if now is None and time.time() - _last_refresh < min_interval:
        return 0
    _last_refresh = time.time()
    today = (now or datetime.now(tz=ET)).astimezone(ET).date()

    with _lock:
        records = _load()
    pending = [r for r in records if not r.get("final")]
    if not pending:
        return 0

    symbols = sorted({r["symbol"] for r in pending})
    recent = sorted({
        r["symbol"] for r in pending
        if (today - date.fromisoformat(r["date"])).days <= 6
        and not {"m15", "h1"} <= set(r.get("outcome") or {})
    })
    try:
        daily = client.get_multi_bars(symbols, days=40)
        bars5: dict[str, pd.DataFrame] = {}
        if recent:
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
            bars5 = client.get_multi_bars(
                recent, timeframe=TimeFrame(5, TimeFrameUnit.Minute), days=8
            )
    except Exception as e:
        logger.warning("Scorecard: price data unavailable: %s", str(e)[:160])
        return 0

    changed = 0
    by_id = {r["id"]: r for r in pending}
    for rid, r in by_id.items():
        try:
            new = evaluate(r, bars5.get(r["symbol"]), daily.get(r["symbol"]), today)
        except Exception as e:
            logger.debug("Scorecard: evaluate failed for %s: %s", rid, e)
            continue
        age = (today - date.fromisoformat(r["date"])).days
        final = "d5" in new or age > 12        # past 12 days nothing more will arrive
        if new != (r.get("outcome") or {}) or final != r.get("final"):
            r["outcome"], r["final"] = new, final
            changed += 1

    if changed:
        with _lock:
            current = _load()                  # merge: alerts may have been logged meanwhile
            for r in current:
                if r["id"] in by_id:
                    r["outcome"], r["final"] = by_id[r["id"]]["outcome"], by_id[r["id"]]["final"]
            _save(current)
    return changed


# ------------------------------------------------------------------ summary

def summarize(records: list[dict]) -> list[dict]:
    """Per kind and direction: how many alerts, and for each horizon the
    number measured, the share that went the alert's way, and the average
    signed move."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        groups.setdefault((r["kind"], r["direction"]), []).append(r)
    rows = []
    for (kind, direction), items in groups.items():
        row: dict = {"kind": kind, "direction": direction, "alerts": len(items)}
        for h in HORIZONS:
            vals = [r["outcome"][h] for r in items if h in (r.get("outcome") or {})]
            row[h] = {
                "n": len(vals),
                "win_pct": round(sum(v > 0 for v in vals) / len(vals) * 100, 0) if vals else None,
                "avg_pct": round(sum(vals) / len(vals), 2) if vals else None,
            }
        touches = [r["outcome"]["first_touch"] for r in items
                   if "first_touch" in (r.get("outcome") or {})]
        row["first_touch"] = {
            "n": len(touches),
            "target": touches.count("target"), "stop": touches.count("stop"),
            "neither": touches.count("neither"),
        } if touches else None
        rows.append(row)
    rows.sort(key=lambda r: r["alerts"], reverse=True)
    return rows


def report(days: int = 30, refresh: bool = True) -> dict:
    """Summary plus the most recent alerts, for the API."""
    if refresh:
        try:
            refresh_outcomes()
        except Exception as e:
            logger.warning("Scorecard refresh failed: %s", str(e)[:160])
    cutoff = (datetime.now(tz=ET).date() - timedelta(days=days)).isoformat()
    records = [r for r in _load() if r.get("date", "") >= cutoff]
    recent = sorted(records, key=lambda r: r["ts"], reverse=True)[:150]
    return {
        "days": days,
        "total_alerts": len(records),
        "first_date": min((r["date"] for r in records), default=""),
        "summary": summarize(records),
        "recent": recent,
        "horizons": {"m15": "15 min", "h1": "1 hour", "eod": "Close", "d1": "+1 day", "d5": "+5 days"},
    }
