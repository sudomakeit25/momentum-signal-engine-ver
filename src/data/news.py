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
        tagged = [str(x).upper() for x in (getattr(n, "symbols", None) or [])]
        created = getattr(n, "created_at", None)
        row = {
            "headline": str(getattr(n, "headline", "") or "")[:220],
            "source": str(getattr(n, "source", "") or ""),
            "time": created.isoformat() if created else "",
            "url": str(getattr(n, "url", "") or ""),
            "specific": len(tagged) <= 3,
        }
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
