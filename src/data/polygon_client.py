"""Polygon.io options data client.

Free tier: 5 API calls per minute, delayed data only.
Uses the snapshot endpoint to get all options for a symbol in one call.
"""

import logging
from datetime import datetime, timedelta

import requests

from config.settings import settings
from src.data.cache import Cache
from src.data.rate_limiter import RateLimiter

logger = logging.getLogger("mse.polygon")

_cache = Cache()
_limiter = RateLimiter(max_calls=5, period_seconds=60)
_BASE = "https://api.polygon.io"


def _get(url: str, params: dict | None = None, cache_key: str | None = None) -> dict | list | None:
    """Make a rate-limited, cached GET request to Polygon."""
    if not settings.polygon_api_key:
        logger.warning("Polygon API key not configured")
        return None

    if cache_key:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

    _limiter.acquire()  # Block until allowed (5/min)

    params = params or {}
    params["apiKey"] = settings.polygon_api_key

    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code == 429:
            logger.warning("Polygon rate limited")
            return None
        if resp.status_code != 200:
            logger.warning("Polygon %s returned %d", url, resp.status_code)
            return None
        data = resp.json()
        if cache_key and data:
            _cache.set(cache_key, data)
        return data
    except Exception as e:
        logger.warning("Polygon error: %s", e)
        return None


def get_options_snapshot(symbol: str) -> list[dict]:
    """Get snapshot of all options contracts for a symbol.

    Returns all contracts with volume, OI, IV, greeks in a single API call.
    This is the most efficient endpoint for the 5 calls/min limit.
    """
    cache_key = f"polygon_snap_{symbol}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    all_contracts = []
    url = f"{_BASE}/v3/snapshot/options/{symbol}"
    params = {"limit": 250}

    data = _get(url, params=params, cache_key=None)
    if not data or "results" not in data:
        return []

    all_contracts.extend(data.get("results", []))

    # Paginate if needed (but usually one page is enough for free tier)
    next_url = data.get("next_url")
    if next_url and len(all_contracts) < 1000:
        more = _get(next_url, cache_key=None)
        if more and "results" in more:
            all_contracts.extend(more["results"])

    if all_contracts:
        _cache.set(cache_key, all_contracts)
        logger.info("Polygon: fetched %d options contracts for %s", len(all_contracts), symbol)

    return all_contracts


def get_options_chain(symbol: str, expiration_gte: str | None = None) -> list[dict]:
    """Get options chain for a symbol with optional expiration filter."""
    cache_key = f"polygon_chain_{symbol}_{expiration_gte}"

    if not expiration_gte:
        expiration_gte = datetime.now().strftime("%Y-%m-%d")

    url = f"{_BASE}/v3/reference/options/contracts"
    params = {
        "underlying_ticker": symbol,
        "expiration_date.gte": expiration_gte,
        "expired": "false",
        "limit": 250,
        "order": "desc",
        "sort": "volume",
    }

    data = _get(url, params=params, cache_key=cache_key)
    if not data or "results" not in data:
        return []
    return data["results"]


def get_ticker_details(symbol: str) -> dict | None:
    """Get basic ticker info (used to verify symbol exists)."""
    cache_key = f"polygon_ticker_{symbol}"
    data = _get(f"{_BASE}/v3/reference/tickers/{symbol}", cache_key=cache_key)
    if data and "results" in data:
        return data["results"]
    return None
