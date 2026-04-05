"""Financial Modeling Prep (FMP) API client.

Free tier: 250 calls/day. Provides earnings calendar, EPS surprises,
analyst estimates, and insider trading data.
"""

import logging
from datetime import datetime, timedelta

import requests

from config.settings import settings
from src.data.cache import Cache
from src.data.rate_limiter import RateLimiter

logger = logging.getLogger("mse.fmp")

_cache = Cache()
_limiter = RateLimiter(max_calls=240, period_seconds=86400)  # 240/day (10 buffer)
_BASE = "https://financialmodelingprep.com/api/v3"


def _get(endpoint: str, params: dict | None = None, cache_key: str | None = None, cache_ttl: int | None = None) -> list | dict | None:
    """Make a rate-limited, cached GET request to FMP."""
    if not settings.fmp_api_key:
        logger.warning("FMP API key not configured")
        return None

    if cache_key:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

    if not _limiter.try_acquire():
        logger.warning("FMP rate limit reached (240/day)")
        return None

    params = params or {}
    params["apikey"] = settings.fmp_api_key

    try:
        resp = requests.get(f"{_BASE}{endpoint}", params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning("FMP %s returned %d", endpoint, resp.status_code)
            return None
        data = resp.json()
        if cache_key and data:
            _cache.set(cache_key, data)
        return data
    except Exception as e:
        logger.warning("FMP error for %s: %s", endpoint, e)
        return None


def get_earnings_calendar(days_ahead: int = 14) -> list[dict]:
    """Get upcoming earnings dates for the next N days."""
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    cache_key = f"fmp_earnings_cal_{today}_{end}"

    data = _get(
        "/earning_calendar",
        params={"from": today, "to": end},
        cache_key=cache_key,
    )
    return data or []


def get_earnings_surprises(symbol: str) -> list[dict]:
    """Get historical EPS surprises for a symbol (last 4-8 quarters)."""
    cache_key = f"fmp_surprises_{symbol}"
    data = _get(
        f"/earnings-surprises/{symbol}",
        cache_key=cache_key,
    )
    return data or []


def get_analyst_estimates(symbol: str) -> list[dict]:
    """Get analyst estimates (annual and quarterly)."""
    cache_key = f"fmp_estimates_{symbol}"
    data = _get(
        f"/analyst-estimates/{symbol}",
        params={"limit": 8},
        cache_key=cache_key,
    )
    return data or []


def get_analyst_estimate_revisions(symbol: str) -> list[dict]:
    """Get recent analyst estimate revisions."""
    cache_key = f"fmp_revisions_{symbol}"
    data = _get(
        f"/analyst-estimates/{symbol}",
        params={"limit": 4, "period": "quarter"},
        cache_key=cache_key,
    )
    return data or []


def get_insider_trades(symbol: str, limit: int = 20) -> list[dict]:
    """Get insider trading activity for a symbol."""
    cache_key = f"fmp_insider_{symbol}_{limit}"
    # Use v4 endpoint for insider trading
    if not settings.fmp_api_key:
        return []

    if not _limiter.try_acquire():
        logger.warning("FMP rate limit reached")
        return []

    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            "https://financialmodelingprep.com/api/v4/insider-trading",
            params={"symbol": symbol, "limit": limit, "apikey": settings.fmp_api_key},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("FMP insider-trading returned %d", resp.status_code)
            return []
        data = resp.json()
        if data:
            _cache.set(cache_key, data)
        return data or []
    except Exception as e:
        logger.warning("FMP insider error for %s: %s", symbol, e)
        return []


def get_stock_grade(symbol: str) -> list[dict]:
    """Get analyst ratings/grades for a symbol."""
    cache_key = f"fmp_grade_{symbol}"
    data = _get(
        f"/grade/{symbol}",
        params={"limit": 10},
        cache_key=cache_key,
    )
    return data or []
