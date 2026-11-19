"""Alerts from the probability map, to Telegram (full text) and SMS (short).

- Evening digest: once per finished session (from 16:25 New York time until
  the next session opens), each watched stock's key levels and odds, the
  10%-close odds, how the session's odds turned out, and the live record.
- Volatility shift: with the digest, when a stock starts moving
  MAP_VOL_SHIFT_RATIO times its usual (or that much less); at most once a
  week per stock.
- Big open: 9:45-10:30 on trading days, once per stock per day, when the
  odds of a 10% close from the open are MAP_OPEN_ALERT_RATIO times what the
  map gave at the previous close (so it reflects the opening gap, not just a
  volatile stretch), with that stock's track record for those odds.
- Price levels: levels the owner sets on the Notifications page, checked
  every minute in regular hours (Alpaca's calendar, so half-days end early)
  from real-time IEX 1-minute bars; one alert per level, the first time it
  trades after it was set.

Each alert is marked sent (in memory and in Redis) before it goes out, so a
failed save or a crash can repeat it at most once after a restart, never
every loop. Every alert describes past frequencies; none is a forecast. Delivery goes
through dispatcher.dispatch_map_alert (auto-alert switch, SMS consent,
duplicate guard). State and levels live in Redis (memory when Redis is not
configured).
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd

from config.settings import settings
from src.scanner import map_record
from src.scanner import probability_map as pm

logger = logging.getLogger("mse.map_alerts")

ET = ZoneInfo("America/New_York")
STATE_KEY = "mse:pmap:alerts"     # {"digest": date, "open": {date: [symbols]}, "vol": {symbol: {...}}}
LEVELS_KEY = "mse:pmap:levels"    # {symbol: [{price, side, ref, added, hit}]}
SESSION_OPEN = dtime(9, 30)
SESSION_CLOSE = dtime(16, 0)
DIGEST_UNTIL = dtime(9, 25)       # a session's digest is sent until the next session opens
OPEN_FROM, OPEN_UNTIL = dtime(9, 45), dtime(10, 30)
LEVEL_TICK = 60                   # seconds between price-level checks in regular hours
LEVEL_START_DELAY = 60
MAX_LEVELS_PER_STOCK = 10
MAX_LEVELS = 50
LEVEL_RANGE = (0.3, 3.0)          # a level must lie within this multiple of the last price
LEVEL_MIN_GAP = 0.001             # and at least 0.1% away from it
VOL_QUIET_DAYS = 7
MIN_OPEN_ODDS = 0.05
DIGEST_LEVELS = (10.0, 5.0, -5.0, -10.0)
SMS_MAX = 155
SMS_TEXTS = 3                     # dispatcher.MAP_SMS_PER_ALERT

_mem: dict[str, str] = {}
_levels_lock = threading.Lock()   # the API and the checker both change the levels
_digest_done_for: str | None = None
_open_done: dict[str, set] = {}   # date -> stocks already checked at the open (memory copy)
_closes: dict[str, dtime] = {}    # date -> that session's close (Alpaca's calendar)


def session_close(day: date) -> dtime:
    """The session's closing time from Alpaca's calendar (13:00 on half-days);
    16:00 when the calendar cannot be read."""
    key = day.isoformat()
    if key not in _closes:
        close = SESSION_CLOSE
        try:
            from alpaca.trading.requests import GetCalendarRequest
            from src.data.client import _get_trading_client
            days = _get_trading_client().get_calendar(GetCalendarRequest(start=day, end=day))
            if days:
                c = days[0].close
                close = c.time() if hasattr(c, "time") else close
        except Exception as e:
            logger.debug("Calendar unreadable for %s: %s", day, e)
        _closes[key] = close
    return _closes[key]


# ---------------------------------------------------------------- storage

def _redis():
    from src.data.redis_store import _get_redis
    return _get_redis()


def _load(key: str, default):
    r = _redis()
    raw = r.get(key) if r is not None else _mem.get(key)
    return json.loads(raw) if raw else default


def _save(key: str, value) -> None:
    raw = json.dumps(value, separators=(",", ":"))
    r = _redis()
    if r is not None:
        r.set(key, raw)
    else:
        _mem[key] = raw


def _send(kind: str, telegram: str, sms: list[str]) -> dict:
    from src.notifications.dispatcher import dispatch_map_alert
    return dispatch_map_alert(kind, telegram, sms)


# ---------------------------------------------------------------- wording

def _p(x) -> str:
    if x is None:
        return "--"
    if 0 < x < 0.01:
        return "<1%"
    if 0.99 < x < 1:
        return ">99%"
    return f"{x * 100:.0f}%"


def _money(v: float) -> str:
    return f"${v:,.2f}" if v >= 1 else f"${v:.4f}"


def _lvl(v: float) -> str:
    return f"{v:+.0f}%"


def _day(d: date) -> str:
    return f"{d.strftime('%a %b')} {d.day}"


def _clock(t: datetime) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def _pack(header: str, lines: list[str], limit: int = SMS_MAX) -> list[str]:
    """Lines packed into texts of at most `limit` characters; the header
    starts the first."""
    texts, cur = [], header
    for line in lines:
        cand = f"{cur}\n{line}" if cur else line
        if len(cand) <= limit:
            cur = cand
        else:
            if cur:
                texts.append(cur)
            cur = line[:limit]
    if cur:
        texts.append(cur)
    return texts


def watchlist() -> list[str]:
    extra = [s.strip().upper() for s in (settings.map_alert_symbols or "").split(",") if s.strip()]
    return list(dict.fromkeys(list(map_record.FOCUS) + [s for s in extra if pm._SYMBOL.match(s)]))


def _trading_day(day: date) -> bool:
    from src.notifications import alert_rules
    return alert_rules.trading_day(day)


def _daily(sym: str, until: date):
    from src.data import client
    d = pm.clean_bars(client.get_multi_bars([sym], days=pm.HISTORY_DAYS).get(sym))
    return d[[x <= until for x in d.index]] if not d.empty else d


# ---------------------------------------------------------------- evening digest

def stock_info(sym: str, as_of: date) -> dict | None:
    """One stock's map from the session's close, the session's high, low and
    close against the session before, and what that session's map had given
    the +-5% and +-10% levels. None when the stock has no bar that session."""
    d = _daily(sym, as_of)
    if d.empty or d.index[-1] != as_of or len(d) < 2:
        return None
    m = pm.build(d, check=False)
    if not m.get("data_ok"):
        return None
    prev = pm.build(d.iloc[:-1], check=False)
    c0 = float(d["close"].iloc[-2])
    row = d.iloc[-1]
    session = {"high": (row["high"] / c0 - 1) * 100, "low": (row["low"] / c0 - 1) * 100,
               "close": (row["close"] / c0 - 1) * 100}
    levels = []
    if prev.get("data_ok"):
        for r in prev["rows"]:
            lvl = r["level_pct"]
            if lvl in DIGEST_LEVELS:
                hit = session["high"] >= lvl if lvl > 0 else session["low"] <= lvl
                levels.append({"level": lvl, "odds": r["odds"][0], "hit": bool(hit)})
    try:
        earnings = pm._earnings(sym, as_of)
    except Exception:
        earnings = None
    return {"symbol": sym, "map": m, "session": session, "levels": levels, "earnings": earnings}


def format_digest(as_of: date, stocks: list[dict], record: dict | None) -> tuple[str, list[str]]:
    """(Telegram text, SMS texts) for the evening digest."""
    lines = [f"MSE probability map, {_day(as_of)} close",
             "Odds of trading at or beyond each level in regular hours: next session / within 5 sessions."]
    sms_lines = []
    for s in stocks:
        m = s["map"]
        rows = {r["level_pct"]: r for r in m["rows"]}
        b = m["big_day"]
        lines.append("")
        lines.append(f"{s['symbol']} {_money(m['last_close'])} ({s['session']['close']:+.1f}% today), "
                     f"moving {m['vol_pct']:.1f}%/day (usual {m['vol_usual_pct']:.1f}%)")
        cells = [f"{_lvl(lvl)} {_money(rows[lvl]['price'])}: {_p(rows[lvl]['odds'][0])} / {_p(rows[lvl]['odds'][1])}"
                 for lvl in DIGEST_LEVELS if lvl in rows]
        lines.append("  " + "   ".join(cells[:2]))
        lines.append("  " + "   ".join(cells[2:]))
        lines.append(f"  10%+ close next session: up {_p(b['up'])}, down {_p(b['down'])} "
                     f"(usual {_p(b['usual_up'])}, {_p(b['usual_down'])})")
        if s["levels"]:
            hit = [f"{_lvl(x['level'])} (had {_p(x['odds'])})" for x in s["levels"] if x["hit"]]
            missed = [f"{_lvl(x['level'])} ({_p(x['odds'])})" for x in s["levels"] if not x["hit"]]
            ses = s["session"]
            text = f"  Today: high {ses['high']:+.1f}%, low {ses['low']:+.1f}%."
            text += f" Reached {', '.join(hit)}." if hit else ""
            text += f" Not reached: {', '.join(missed)}." if missed else ""
            lines.append(text)
        e = s.get("earnings") or {}
        if e.get("date") and e.get("sessions_away") is not None and e["sessions_away"] <= 20:
            lines.append(f"  Earnings expected {e['date']}, {e['sessions_away']} sessions away "
                         "(the map does not single out earnings days).")
        r5, r_5 = rows.get(5.0), rows.get(-5.0)
        if r5 and r_5:
            sms_lines.append(f"{s['symbol']} {m['last_close']:.2f}: +5% {_p(r5['odds'][0])}/{_p(r5['odds'][1])}, "
                             f"-5% {_p(r_5['odds'][0])}/{_p(r_5['odds'][1])}, 10%cls {_p(b['up'])}/{_p(b['down'])}")
    lines.append("")
    lines.append(_record_line(record))
    lines.append("Past frequencies, not forecasts.")
    sms = _pack(f"MSE odds {as_of.month}/{as_of.day} (next/5 sessions)", sms_lines)
    if len(sms) > SMS_TEXTS:                        # the rest would be dropped: say where they are
        shown = sum(t.count("\n") + 1 for t in sms[:SMS_TEXTS]) - 1
        more = f"+{len(sms_lines) - shown} more stocks on Telegram"
        last = sms[SMS_TEXTS - 1]
        sms = sms[:SMS_TEXTS - 1] + [(last if len(last) + len(more) + 1 <= SMS_MAX
                                      else last[:SMS_MAX - len(more) - 1]) + "\n" + more]
    return "\n".join(lines), sms


def _record_line(record: dict | None) -> str:
    pooled = (record or {}).get("pooled")
    if not pooled:
        return "Live record: nothing scored yet."
    n = pooled["days"].get("1", 0)
    if pooled.get("verdict"):
        return (f"Live record ({n} sessions scored, all stocks): the map was {pooled['verdict']}.")
    return f"Live record: {n} {'session' if n == 1 else 'sessions'} scored; too early to judge (needs {pooled['min_days']})."


def vol_shifts(stocks: list[dict], state: dict, today: date) -> list[dict]:
    """Stocks whose volatility has moved into 'high' (MAP_VOL_SHIFT_RATIO x
    usual or more) or 'low' (1/x or less) since the last digest, at most once
    per VOL_QUIET_DAYS each. Updates state["vol"]."""
    r = max(float(settings.map_vol_shift_ratio), 1.01)
    vol = state.setdefault("vol", {})
    out = []
    for s in stocks:
        m = s["map"]
        if not m.get("vol_usual_pct"):
            continue
        ratio = m["vol_pct"] / m["vol_usual_pct"]
        new = "high" if ratio >= r - 1e-9 else "low" if ratio <= 1 / r + 1e-9 else "normal"   # inclusive
        prev = vol.get(s["symbol"], {})
        sent = prev.get("sent")
        quiet = sent is None or (today - date.fromisoformat(sent)).days >= VOL_QUIET_DAYS
        entry = {"state": new, "sent": sent}
        if new != "normal" and new != prev.get("state", "normal") and quiet:
            out.append({"symbol": s["symbol"], "state": new, "ratio": ratio, "map": m})
            entry["sent"] = str(today)
        vol[s["symbol"]] = entry
    return out


def format_vol_shift(x: dict) -> tuple[str, list[str]]:
    m, sym = x["map"], x["symbol"]
    rows = {r["level_pct"]: r for r in m["rows"]}
    up, dn = rows[10.0], rows[-10.0]
    i20 = len(m["horizons"]) - 1
    wider = "widened" if x["state"] == "high" else "narrowed"
    tg = (f"MSE: {sym} is moving {x['ratio']:.1f}x its usual: {m['vol_pct']:.1f}% a day against "
          f"{m['vol_usual_pct']:.1f}%. Its odds have {wider}: +10% within 20 sessions {_p(up['odds'][i20])} "
          f"(usual {_p(up['usual'][i20])}), -10% {_p(dn['odds'][i20])} (usual {_p(dn['usual'][i20])}). "
          "Past frequencies, not a forecast.")
    sms = (f"MSE {sym} moving {x['ratio']:.1f}x usual ({m['vol_pct']:.1f}%/day): +10% in 20 sessions "
           f"{_p(up['odds'][i20])} (usual {_p(up['usual'][i20])}), -10% {_p(dn['odds'][i20])} ({_p(dn['usual'][i20])})")
    return tg, [sms]


def _fresh(as_of: date, now_et: datetime) -> bool:
    """A session's digest is worth sending until the next session opens."""
    if now_et.date() == as_of or now_et.time() < DIGEST_UNTIL:
        return True
    return not _trading_day(now_et.date())


def evening_due(now: datetime | None = None) -> bool:
    """Cheap check outside the heavy-step lock: alerts on, a session has
    finished since the last digest this process sent, and it is not too late."""
    global _digest_done_for
    if not settings.map_alerts_enabled:
        return False
    now_et = (now or datetime.now(ET)).astimezone(ET)
    cal = map_record.sessions(now_et)
    if not cal or _digest_done_for == str(cal[-1]):
        return False
    if not _fresh(cal[-1], now_et):
        _digest_done_for = str(cal[-1])           # too late for that session's digest
        return False
    return True


def evening(now: datetime | None = None) -> str | None:
    """Send the digest (and any volatility-shift alerts) for the last
    finished session, once. Returns a summary, or None."""
    global _digest_done_for
    now_et = (now or datetime.now(ET)).astimezone(ET)
    cal = map_record.sessions(now_et)
    if not cal:
        return None
    as_of = cal[-1]
    if _digest_done_for == str(as_of):
        return None
    if not _fresh(as_of, now_et):                   # e.g. waited for the heavy-step lock past the open
        _digest_done_for = str(as_of)
        return None
    state = _load(STATE_KEY, {})
    if state.get("digest") == str(as_of):
        _digest_done_for = str(as_of)
        return None
    stocks = []
    for sym in watchlist():
        try:
            info = stock_info(sym, as_of)
        except Exception as e:
            logger.warning("Map digest: %s skipped: %s", sym, str(e)[:120])
            info = None
        if info:
            stocks.append(info)
    if not stocks:
        return None                                 # no data yet; tried again next pass
    tg, sms = format_digest(as_of, stocks, map_record.report())
    shifts = vol_shifts(stocks, state, now_et.date())
    # Marked sent before sending: a failed save then costs at most one repeat
    # after a restart, never one every loop.
    state["digest"] = str(as_of)
    _digest_done_for = str(as_of)
    try:
        _save(STATE_KEY, state)
    except Exception as e:
        logger.warning("Map digest state not saved (%s); sending once", type(e).__name__)
    res = _send("digest", tg, sms)
    for x in shifts:
        _send("vol_shift", *format_vol_shift(x))
    return (f"digest for {as_of}: {len(stocks)} stocks, telegram {'sent' if res['telegram'] else 'not sent'}, "
            f"{res['sms']} texts" + (f"; volatility shifts: {', '.join(x['symbol'] for x in shifts)}" if shifts else ""))


# ---------------------------------------------------------------- big open

def open_alert(m: dict) -> tuple[str, list[str]] | None:
    """The alert for one stock's map once today's open is known, or None
    when its odds of a 10% close are not MAP_OPEN_ALERT_RATIO times usual."""
    td, b = m.get("today"), m.get("big_day")
    if not td or not b:
        return None
    r = float(settings.map_open_alert_ratio)
    sides = []
    for side, p, c, u in (("up", td.get("up"), b.get("up"), b.get("usual_up")),
                          ("down", td.get("down"), b.get("down"), b.get("usual_down"))):
        # Against the previous close's odds, which already reflect how much
        # the stock is moving, so only the opening gap can set it off.
        if p is not None and c is not None and p >= MIN_OPEN_ODDS and p >= r * c:
            sides.append((side, p, c, u))
    if not sides:
        return None
    sym, prev, opn, gap = m["symbol"], m["last_close"], td["open"], td["gap_pct"]
    track = ((m.get("calibration") or {}).get("big_day") or {}).get("open_verdict")
    parts = []
    for side, p, c, u in sides:
        target = prev * (1.1 if side == "up" else 0.9)
        parts.append(f"closing 10%+ {side} today ({'at or above' if side == 'up' else 'at or below'} "
                     f"{_money(target)}): {_p(p)}, against {_p(c)} at the previous close (usual {_p(u)})")
    tg = (f"MSE: {sym} opened {gap:+.1f}% at {_money(opn)} (previous close {_money(prev)}). "
          f"Chance of {'; '.join(parts)}.")
    if track:
        tg += f" For {sym}, odds from the open have been {track} over the last 500 sessions."
    tg += " Past frequencies, not a forecast."
    side, p, c, u = sides[0]
    sms = f"MSE {sym} opened {gap:+.1f}% {_money(opn)}: 10%+ close {side} today {_p(p)} (was {_p(c)})."
    if track:
        sms += f" Open odds for {sym}: {track.replace(' its usual odds', ' usual')}."
    return tg, [sms]


def open_due(now: datetime | None = None) -> bool:
    now_et = (now or datetime.now(ET)).astimezone(ET)
    return (settings.map_alerts_enabled and now_et.weekday() < 5
            and OPEN_FROM <= now_et.time() < OPEN_UNTIL)


def open_tick(now: datetime | None = None) -> list[str]:
    """Check each watched stock once its open is in; alert when the odds of
    a 10% close are well above usual. Once per stock per day."""
    now_et = (now or datetime.now(ET)).astimezone(ET)
    today = str(now_et.date())
    if not _trading_day(now_et.date()):
        return []
    state = _load(STATE_KEY, {})
    done = _open_done.setdefault(today, set())
    done |= set((state.get("open") or {}).get(today, []))
    for day in [d for d in _open_done if d != today]:
        _open_done.pop(day, None)
    sent = []
    for sym in watchlist():
        if sym in done:
            continue
        try:
            m = pm.probability_map(sym, now=now_et, background=True)   # pages come first
        except Exception as e:
            logger.warning("Open odds check failed for %s: %s", sym, str(e)[:120])
            continue
        if not m.get("data_ok") or not m.get("in_progress") or not m.get("today"):
            continue                                  # open not in yet, or busy; next pass
        done.add(sym)                                 # marked before anything is sent
        state["open"] = {today: sorted(done)}
        try:
            _save(STATE_KEY, state)
        except Exception as e:
            logger.warning("Big-open state not saved (%s)", type(e).__name__)
        alert = open_alert(m)
        if alert:
            _send("open", *alert)
            sent.append(sym)
    return sent


# ---------------------------------------------------------------- price levels

def list_levels() -> dict:
    try:
        levels = _load(LEVELS_KEY, {})
    except Exception as e:
        logger.warning("Price levels read failed: %s", str(e)[:120])
        return {"ok": False, "note": "Could not read the price alerts right now.", "levels": []}
    rows = [{"symbol": sym, **lvl} for sym, lst in sorted(levels.items()) for lvl in lst]
    return {"ok": True, "levels": rows}


def _last_price(sym: str, now_et: datetime | None = None) -> float | None:
    """The latest price: today's latest IEX minute in regular hours (real
    time), otherwise the last daily close."""
    from src.notifications import alert_rules
    now_et = (now_et or datetime.now(ET)).astimezone(ET)
    if alert_rules.market_open(now_et) and now_et.time() < session_close(now_et.date()):
        try:
            b = session_bars([sym], now_et).get(sym)
            if b is not None and not b.empty:
                return float(b["close"].iloc[-1])
        except Exception as e:
            logger.debug("IEX price unavailable for %s: %s", sym, e)
    from src.data import client
    d = pm.clean_bars(client.get_multi_bars([sym], days=10).get(sym))
    return float(d["close"].iloc[-1]) if not d.empty else None


def add_level(symbol: str, price, now: datetime | None = None) -> dict:
    """Add a price level for a stock. Which side it is on (above or below)
    is fixed from the latest price when it is added."""
    sym = (symbol or "").strip().upper()
    if not pm._SYMBOL.match(sym):
        return {"ok": False, "note": "Not a stock symbol."}
    try:
        price = float(price)
    except (TypeError, ValueError):
        return {"ok": False, "note": "Not a price."}
    if not math.isfinite(price) or price <= 0:
        return {"ok": False, "note": "Not a price."}
    now_et = (now or datetime.now(ET)).astimezone(ET)
    try:
        ref = _last_price(sym, now_et)
    except Exception:
        ref = None
    if not ref:
        return {"ok": False, "note": f"No recent price for {sym}."}
    lo, hi = LEVEL_RANGE
    if not lo * ref <= price <= hi * ref:
        return {"ok": False, "note": f"{_money(price)} is too far from {sym}'s last price {_money(ref)}."}
    if abs(price / ref - 1) < LEVEL_MIN_GAP:
        return {"ok": False, "note": f"{_money(price)} is right at {sym}'s last price {_money(ref)}."}
    level = {"price": round(price, 4), "side": "above" if price > ref else "below", "ref": round(ref, 4),
             "added": now_et.isoformat(timespec="minutes"), "hit": None}
    with _levels_lock:
        levels = _load(LEVELS_KEY, {})
        mine = levels.setdefault(sym, [])
        if any(abs(x["price"] - level["price"]) < 1e-6 and not x.get("hit") for x in mine):
            return {"ok": True, "note": "Already set.", "level": {"symbol": sym, **level}}
        if sum(1 for x in mine if not x.get("hit")) >= MAX_LEVELS_PER_STOCK:
            return {"ok": False, "note": f"{sym} already has {MAX_LEVELS_PER_STOCK} waiting levels."}
        if sum(1 for lst in levels.values() for x in lst if not x.get("hit")) >= MAX_LEVELS:
            return {"ok": False, "note": f"There are already {MAX_LEVELS} waiting levels."}
        mine.append(level)
        _save(LEVELS_KEY, levels)
    return {"ok": True, "level": {"symbol": sym, **level}}


def remove_level(symbol: str, price) -> dict:
    sym = (symbol or "").strip().upper()
    try:
        price = float(price)
    except (TypeError, ValueError):
        return {"ok": False, "note": "Not a price."}
    with _levels_lock:
        levels = _load(LEVELS_KEY, {})
        mine = levels.get(sym, [])
        keep = [x for x in mine if abs(x["price"] - price) >= 1e-6]
        if len(keep) == len(mine):
            return {"ok": False, "note": "No such level."}
        if keep:
            levels[sym] = keep
        else:
            levels.pop(sym, None)
        _save(LEVELS_KEY, levels)
    return {"ok": True}


def session_bars(symbols: list[str], now_et: datetime) -> dict[str, pd.DataFrame]:
    """Today's regular-session 1-minute bars from IEX (real time on the free
    plan; IEX trades only)."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from src.data import client
    start = datetime.combine(now_et.date(), SESSION_OPEN, tzinfo=ET)
    req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Minute, start=start, feed=DataFeed.IEX)
    df = client._get_data_client().get_stock_bars(req).df
    out = {}
    if df is None or df.empty:
        return out
    for sym in symbols:
        try:
            sub = df.xs(sym, level="symbol").copy()
        except KeyError:
            continue
        sub.index = pd.to_datetime(sub.index).tz_convert(ET)
        out[sym] = sub[(sub.index >= start) & (sub.index.time < session_close(now_et.date()))]
    return out


def level_context(sym: str, price: float, today: date, side: str) -> dict | None:
    """The map's odds for a level, from the last session before today. The
    map measures moves away from that close, so its odds apply only when
    the level lies on the side it is being approached from: above the close
    for a level reached going up, below it going down. Otherwise the result
    says so ("applies": False) and carries no odds."""
    from datetime import timedelta
    d = _daily(sym, today - timedelta(days=1))
    if d.empty:
        return None
    close = float(d["close"].iloc[-1])
    base = {"close": close, "as_of": d.index[-1], "pct": (price / close - 1) * 100}
    if (side == "above") != (price > close):
        return {**base, "applies": False}
    odds = pm.level_odds(pm.prepare(d), len(d) - 1, price)
    return {**base, **odds, "applies": True} if odds else None


def format_level_hit(sym: str, level: dict, at: datetime, extreme: float, ctx: dict | None) -> tuple[str, list[str]]:
    above = level["side"] == "above"
    word = "high" if above else "low"
    tg = (f"MSE price alert: {sym} traded at {_money(level['price'])} at {_clock(at)} "
          f"(your level; {word} so far {_money(extreme)}).")
    sms = f"MSE {sym} hit {_money(level['price'])} {_clock(at)}"
    if ctx and not ctx.get("applies", True):
        tg += (f" That is {ctx['pct']:+.1f}% from {_day(ctx['as_of'])}'s close of {_money(ctx['close'])}, on the "
               "other side of that close from where it was reached, so the map's odds from that close do not apply.")
        sms += f" ({ctx['pct']:+.1f}% vs prev close)."
    elif ctx:
        w = ctx["within"]
        tg += (f" That is {ctx['pct']:+.1f}% from {_day(ctx['as_of'])}'s close of {_money(ctx['close'])}. "
               f"The map from that close gave it {_p(w[1])} for the next session and {_p(w[5])} within 5 sessions.")
        if ctx.get("held5") is not None:
            tg += (f" In {sym}'s history, of the times it reached a level this far within 5 sessions, "
                   f"{_p(ctx['held5'])} were still {'at or above' if above else 'at or below'} it at the 5th close.")
        sms += f" ({ctx['pct']:+.1f}%). Map odds {_p(w[1])} that day, {_p(w[5])} in 5."
        if ctx.get("held5") is not None:
            sms += f" Past touches held 5 days: {_p(ctx['held5'])}."
    tg += " IEX real-time prices. Past frequencies, not a forecast."
    return tg, [sms[:SMS_MAX]]


def check_levels(now: datetime | None = None) -> list[str]:
    """Alert each waiting level the first time it trades in today's regular
    session. Marks it hit before sending, so it is alerted at most once."""
    from src.notifications import alert_rules
    now_et = (now or datetime.now(ET)).astimezone(ET)
    if not alert_rules.market_open(now_et) or now_et.time() >= session_close(now_et.date()):
        return []
    with _levels_lock:
        levels = _load(LEVELS_KEY, {})
    waiting = {s: [x for x in lst if not x.get("hit")] for s, lst in levels.items()}
    waiting = {s: lst for s, lst in waiting.items() if lst}
    if not waiting:
        return []
    bars = session_bars(sorted(waiting), now_et)
    hits = []
    for sym, lst in waiting.items():
        b = bars.get(sym)
        if b is None or b.empty:
            continue
        for x in lst:
            try:                                        # only trades after the level was set count
                added = datetime.fromisoformat(x["added"]).astimezone(ET)
                after = b[b.index > added]
            except (KeyError, TypeError, ValueError):
                after = b
            if after.empty:
                continue
            col = after["high"] if x["side"] == "above" else after["low"]
            mask = (col >= x["price"]) if x["side"] == "above" else (col <= x["price"])
            if mask.any():
                at = mask.idxmax()
                extreme = float(col.max() if x["side"] == "above" else col.min())
                hits.append((sym, x, at, extreme))
    if not hits:
        return []
    with _levels_lock:
        levels = _load(LEVELS_KEY, {})                 # read again: the page may have changed it
        marked = []
        for sym, x, at, extreme in hits:
            for y in levels.get(sym, []):
                if abs(y["price"] - x["price"]) < 1e-6 and not y.get("hit"):
                    y["hit"] = {"at": at.isoformat(timespec="minutes"), "extreme": round(extreme, 4)}
                    marked.append((sym, y, at, extreme))
        _save(LEVELS_KEY, levels)
    out = []
    for sym, y, at, extreme in marked:
        try:
            ctx = level_context(sym, y["price"], now_et.date(), y["side"])
        except Exception as e:
            logger.warning("Level odds failed for %s: %s", sym, str(e)[:120])
            ctx = None
        _send("level", *format_level_hit(sym, y, at, extreme, ctx))
        out.append(f"{sym} {_money(y['price'])}")
    return out


def run_levels(stop: threading.Event) -> None:
    """Background thread: check the price levels every LEVEL_TICK seconds in
    regular hours. Never raises."""
    if stop.wait(LEVEL_START_DELAY):
        return
    while not stop.is_set():
        try:
            if settings.map_alerts_enabled:
                hit = check_levels()
                if hit:
                    logger.info("Price alerts: %s", ", ".join(hit))
        except Exception as e:
            logger.warning("Price level check failed: %s", str(e)[:160])
        stop.wait(LEVEL_TICK)
