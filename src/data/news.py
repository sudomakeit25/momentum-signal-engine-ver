"""Recent headlines per symbol, from Alpaca's news feed (Benzinga).

Used to put a reason next to a mover. A headline tagged with one or two
symbols is about that company; one tagged with a dozen is a market wrap, so
specific headlines are ranked first.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from config.settings import settings

logger = logging.getLogger("mse.news")

_TTL = 5 * 60
_MAX_SYMBOLS = 40
_cache: dict[str, tuple[float, list[dict]]] = {}


def _client():
    from alpaca.data.historical.news import NewsClient
    return NewsClient(settings.alpaca_api_key, settings.alpaca_secret_key)


def _fetch(symbols: list[str], since: datetime) -> list:
    from alpaca.data.requests import NewsRequest
    res = _client().get_news(NewsRequest(symbols=",".join(symbols), start=since, limit=50))
    data = getattr(res, "data", None) or {}
    return list(data.get("news", []))


def _row(n) -> tuple[dict, list[str]]:
    """One feed item as a plain row, plus the symbols it is tagged with."""
    tagged = [str(x).upper() for x in (getattr(n, "symbols", None) or [])]
    created = getattr(n, "created_at", None)
    return {
        "headline": str(getattr(n, "headline", "") or "")[:220],
        "source": str(getattr(n, "source", "") or ""),
        "time": created.isoformat() if created else "",
        "url": str(getattr(n, "url", "") or ""),
        "specific": len(tagged) <= 3,
    }, tagged


_RANGE_TTL = 60 * 60
_RANGE_TTL_OPEN = 5 * 60    # a window that has not ended yet still gains headlines
_RANGE_CACHE_MAX = 500      # the caller is a public endpoint, so the cache must be bounded
_range_cache: dict[tuple, tuple[float, list[dict]]] = {}


def _bounded_put(cache: dict, key, value, max_items: int) -> None:
    """Insert, then evict the oldest entries once the cache is over its size."""
    cache[key] = value
    if len(cache) > max_items:
        for old in sorted(cache, key=lambda k: cache[k][0])[: len(cache) - max_items]:
            cache.pop(old, None)


def _fetch_range(symbol: str, start: datetime, end: datetime) -> list:
    from alpaca.data.requests import NewsRequest
    res = _client().get_news(NewsRequest(symbols=symbol, start=start, end=end, limit=50))
    data = getattr(res, "data", None) or {}
    return list(data.get("news", []))


def headlines_between(symbol: str, start: datetime, end: datetime, limit: int = 3) -> list[dict] | None:
    """Headlines tagged with `symbol` published from `start` to `end`, most
    specific first, then newest. [] means there were none; None means the
    feed could not be read. Never raises."""
    symbol = symbol.upper()
    if "/" in symbol or end <= start:
        return []
    key = (symbol, start.isoformat(), end.isoformat())
    hit = _range_cache.get(key)
    ttl = _RANGE_TTL_OPEN if end > datetime.now(timezone.utc) else _RANGE_TTL
    if hit and time.time() - hit[0] < ttl:
        return hit[1][:limit]
    try:
        items = _fetch_range(symbol, start, end)
    except Exception as e:
        logger.warning("News unavailable: %s", str(e)[:160])
        return None
    rows = []
    for n in items:
        row, tagged = _row(n)
        if row["headline"] and symbol in tagged:
            rows.append(row)
    rows.sort(key=lambda r: (r["specific"], r["time"]), reverse=True)
    _bounded_put(_range_cache, key, (time.time(), rows), _RANGE_CACHE_MAX)
    return rows[:limit]


def latest_headlines(
    symbols: list[str], hours: int = 24, per_symbol: int = 2
) -> dict[str, list[dict]]:
    """{symbol: [{headline, source, time, url, specific}]}, newest and most
    specific first. Symbols with no news are absent. Never raises: news is
    decoration, and a failure must not break the scan it decorates."""
    wanted = list(dict.fromkeys(s.upper() for s in symbols if "/" not in s))[:_MAX_SYMBOLS]
    now = time.time()
    out: dict[str, list[dict]] = {}
    missing = []
    for s in wanted:
        hit = _cache.get(s)
        if hit and now - hit[0] < _TTL:
            if hit[1]:
                out[s] = hit[1][:per_symbol]
        else:
            missing.append(s)
    if not missing:
        return out

    try:
        items = _fetch(missing, datetime.now(timezone.utc) - timedelta(hours=hours))
    except Exception as e:
        logger.warning("News unavailable: %s", str(e)[:160])
        return out

    found: dict[str, list[dict]] = {s: [] for s in missing}
    for n in items:
        row, tagged = _row(n)
        if not row["headline"]:
            continue
        for s in tagged:
            if s in found:
                found[s].append(row)
    for s, rows in found.items():
        rows.sort(key=lambda r: (r["specific"], r["time"]), reverse=True)
        _cache[s] = (now, rows)
        if rows:
            out[s] = rows[:per_symbol]
    return out
