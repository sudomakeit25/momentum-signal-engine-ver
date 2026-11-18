"""Today's most active US stocks, from Alpaca's free screener.

Why: the intraday movers screen (and the paper auto-trader behind it) only
saw about 90 large companies: the watchlist plus the top names by dollar
volume from the daily scan, which itself falls back to a fixed list because
FMP's market-wide screener is not on the free plan. A mid-cap moving on news
never reached the screen. This adds whatever is busiest today.

Ranked by number of trades, not shares traded: share volume is dominated by
sub-dollar stocks and warrants, trade count favours liquid names. The movers
screen still applies all of its own filters (price, average volume, change,
relative volume), so anything unsuitable drops out there.
"""

from __future__ import annotations

import logging
import threading
import time

from config.settings import settings

logger = logging.getLogger("mse.most_actives")

TTL = 5 * 60            # the list changes slowly; one request per scan cycle at most
STALE_OK = 30 * 60      # after a failure, the last good list is used this long
MAX_TOP = 100           # Alpaca's limit for this list

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "symbols": [], "failed_at": 0.0}


def _plain(symbol: str) -> bool:
    """Plain 1-5 letter tickers. Alpaca rejects a whole bars request if one
    symbol is malformed for it, and warrants or units (suffixes) are not
    what the screen is for."""
    return isinstance(symbol, str) and symbol.isalpha() and symbol.isupper() and 1 <= len(symbol) <= 5


def _fetch(top: int) -> list[str]:
    from alpaca.data.enums import MostActivesBy
    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.data.requests import MostActivesRequest
    client = ScreenerClient(settings.alpaca_api_key, settings.alpaca_secret_key)
    res = client.get_most_actives(MostActivesRequest(top=top, by=MostActivesBy.TRADES))
    return [r.symbol for r in (getattr(res, "most_actives", None) or [])]


def most_active(top: int | None = None, now: float | None = None) -> list[str]:
    """Up to `top` of today's most traded plain tickers, busiest first.
    Cached for TTL; on failure the last good list is used for STALE_OK, then
    an empty list. Never raises: the screen works without it."""
    top = max(1, min(MAX_TOP, int(settings.intraday_most_active_top if top is None else top)))
    now = time.time() if now is None else now
    with _lock:
        if _cache["symbols"] and now - _cache["at"] < TTL:
            return _cache["symbols"][:top]
        if now - _cache["failed_at"] < 60:          # do not hammer a failing endpoint
            return _cache["symbols"][:top] if now - _cache["at"] < STALE_OK else []
    try:
        symbols = [s for s in dict.fromkeys(_fetch(MAX_TOP)) if _plain(s)]
    except Exception as e:
        with _lock:
            _cache["failed_at"] = now
            stale = _cache["symbols"] if now - _cache["at"] < STALE_OK else []
        logger.warning("Most-actives list unavailable (%s); using %d cached symbols",
                       str(e)[:120], len(stale))
        return stale[:top]
    with _lock:
        _cache.update(at=now, symbols=symbols, failed_at=0.0)
    return symbols[:top]
