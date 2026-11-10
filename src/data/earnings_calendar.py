"""Who reports earnings today or tomorrow.

Primary source: Nasdaq's public earnings calendar (the feed behind
nasdaq.com/market-activity/earnings). It needs no key and covers the whole
market, with before/after-market timing. It is not a documented API, so it
can change or refuse a server's address; every failure is therefore treated
as "unknown", never as "nobody reports".

Fallback: Financial Modeling Prep, asked one symbol at a time. On the free
plan FMP only answers for a limited set of large companies and refuses the
rest, so a refused symbol stays unknown.

`reporting_soon` returns both the symbols that report and the symbols whose
status is actually known. Callers that act on the answer (the auto-trader)
must skip anything not in the known set.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger("mse.earnings_calendar")

ET = ZoneInfo("America/New_York")
_NASDAQ_URL = "https://api.nasdaq.com/api/calendar/earnings"
_HEADERS = {
    # Nasdaq's edge rejects requests without a browser-like user agent.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
_OK_TTL = 6 * 3600        # a day's calendar barely changes intraday
_FAIL_TTL = 10 * 60       # do not hammer a source that is refusing us
_MAX_FMP_FALLBACK = 30    # symbols per lookup (FMP free tier is 250 calls/day)

# date ISO -> (fetched_at, rows or None)
_day_cache: dict[str, tuple[float, list[dict] | None]] = {}
_last: dict = {"source": "", "nasdaq": {}, "at": ""}


def _money(value) -> float | None:
    """'$6,269,324,300' -> 6269324300.0, '($0.34)' -> -0.34, 'N/A' -> None."""
    if value is None:
        return None
    s = str(value).strip().replace("$", "").replace(",", "")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        number = float(s)
    except ValueError:
        return None
    return -number if negative else number


def _number(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def session_label(time_field: str) -> str:
    """Nasdaq's time field as bmo (before open), amc (after close) or ''."""
    t = (time_field or "").lower()
    if "pre-market" in t:
        return "bmo"
    if "after-hours" in t:
        return "amc"
    return ""


def _nasdaq_fetch(day: date) -> list[dict] | None:
    """Rows for one date, [] if nobody reports, None if the calendar could
    not be read."""
    outcome = {"ok": False, "status": 0, "rows": 0, "message": "", "date": day.isoformat(),
               "at": datetime.now().isoformat(timespec="seconds")}
    try:
        resp = requests.get(_NASDAQ_URL, params={"date": day.isoformat()},
                            headers=_HEADERS, timeout=10)
        outcome["status"] = resp.status_code
        if resp.status_code != 200:
            outcome["message"] = f"HTTP {resp.status_code}"
            return None
        body = resp.json()
        if not isinstance(body, dict):
            outcome["message"] = "unexpected response shape"
            return None
        code = (body.get("status") or {}).get("rCode")
        data = body.get("data")
        if code != 200 or not isinstance(data, dict):
            outcome["message"] = f"calendar refused (rCode {code})"
            return None
        raw = data.get("rows")
        if raw is None:
            raw = []          # a real answer: no earnings on this date
        if not isinstance(raw, list):
            outcome["message"] = "rows is not a list"
            return None
        rows = [
            {
                "symbol": str(r["symbol"]).upper().strip(),
                "time": str(r.get("time") or ""),
                "name": str(r.get("name") or ""),
                "market_cap": _money(r.get("marketCap")),
                "eps_forecast": _money(r.get("epsForecast")),
                # Present only once the company has reported (past dates)
                "eps": _money(r.get("eps")),
                "surprise_pct": _number(r.get("surprise")),
            }
            for r in raw if isinstance(r, dict) and r.get("symbol")
        ]
        outcome.update(ok=True, rows=len(rows))
        return rows
    except Exception as e:
        outcome["message"] = f"{type(e).__name__}"
        return None
    finally:
        # Keyed by date: a good answer for tomorrow must not hide a failed today.
        per_day = dict(_last.get("nasdaq") or {})
        per_day[day.isoformat()] = outcome
        _last["nasdaq"] = dict(sorted(per_day.items())[-4:])
        if not outcome["ok"]:
            logger.warning("Nasdaq earnings calendar unavailable for %s: %s",
                           day.isoformat(), outcome["message"])


def nasdaq_day(day: date) -> list[dict] | None:
    key = day.isoformat()
    cached = _day_cache.get(key)
    if cached is not None:
        fetched_at, rows = cached
        if time.time() - fetched_at < (_OK_TTL if rows is not None else _FAIL_TTL):
            return rows
    rows = _nasdaq_fetch(day)
    _day_cache[key] = (time.time(), rows)
    return rows


def _fmp_lookup(symbols: list[str], days: set[str]) -> tuple[set[str], set[str]]:
    """Per-symbol check with FMP. A symbol FMP refuses is simply not known."""
    from src.data import fmp_client

    reporting: set[str] = set()
    known: set[str] = set()
    for sym in symbols[:_MAX_FMP_FALLBACK]:
        ok, next_date = fmp_client.get_symbol_next_earnings(sym)
        if not ok:
            continue
        known.add(sym)
        if next_date in days:
            reporting.add(sym)
    return reporting, known


def reporting_soon(
    symbols: list[str], now: datetime | None = None
) -> tuple[set[str], set[str]]:
    """(symbols reporting today or tomorrow, symbols whose status is known).

    Both sets are subsets of `symbols`. A symbol outside the second set has
    an unknown status and must not be treated as clear.
    """
    wanted = [s.upper() for s in symbols]
    if not wanted:
        return set(), set()
    today = (now or datetime.now(tz=ET)).astimezone(ET).date()
    days = [today, today + timedelta(days=1)]

    calendars = [nasdaq_day(d) for d in days]
    if all(c is not None for c in calendars):
        listed = {r["symbol"] for c in calendars for r in c}
        _last.update(source="nasdaq", at=datetime.now().isoformat(timespec="seconds"))
        return {s for s in wanted if s in listed}, set(wanted)

    reporting, known = _fmp_lookup(wanted, {d.isoformat() for d in days})
    _last.update(source="fmp (nasdaq unavailable)",
                 at=datetime.now().isoformat(timespec="seconds"))
    return reporting, known


def status() -> dict:
    """Which source answered last and what Nasdaq last said. No secrets."""
    return dict(_last)
