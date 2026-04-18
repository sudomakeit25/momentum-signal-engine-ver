"""Financial Modeling Prep (FMP) API client.

Free tier: 250 calls/day. Provides earnings calendar, EPS surprises,
analyst estimates, and insider trading data.
"""

import logging
import time
from datetime import datetime, timedelta

import requests

from config.settings import settings
from src.data.cache import Cache
from src.data.rate_limiter import RateLimiter

logger = logging.getLogger("mse.fmp")

_cache = Cache()
_limiter = RateLimiter(max_calls=240, period_seconds=86400)  # 240/day (10 buffer)
_BASE = "https://financialmodelingprep.com/api/v3"

_universe_cache: tuple[float, list[str]] | None = None
_UNIVERSE_TTL_SECONDS = 86400  # 24h


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


def get_liquid_universe(
    market_cap_min: int = 300_000_000,
    volume_min: int = 500_000,
    price_min: float = 3.0,
    price_max: float = 10_000.0,
    force_refresh: bool = False,
) -> list[str]:
    """Fetch a dynamic liquid US equity universe from the FMP stock screener.

    Filters by market cap, average volume, price, and US exchanges. Result is
    cached in-process for 24 hours. On cache miss or failure, returns the last
    cached list (or an empty list if none).
    """
    global _universe_cache
    now = time.time()
    if not force_refresh and _universe_cache is not None:
        if now - _universe_cache[0] < _UNIVERSE_TTL_SECONDS:
            return _universe_cache[1]

    if not settings.fmp_api_key:
        logger.warning("FMP API key not configured; liquid universe unavailable")
        return _universe_cache[1] if _universe_cache else []

    if not _limiter.try_acquire():
        logger.warning("FMP rate limit reached; returning stale universe")
        return _universe_cache[1] if _universe_cache else []

    params = {
        "marketCapMoreThan": market_cap_min,
        "volumeMoreThan": volume_min,
        "priceMoreThan": price_min,
        "priceLowerThan": price_max,
        "isActivelyTrading": "true",
        "exchange": "nyse,nasdaq,amex",
        "limit": 10000,
        "apikey": settings.fmp_api_key,
    }
    try:
        resp = requests.get(f"{_BASE}/stock-screener", params=params, timeout=30)
        if resp.status_code != 200:
            logger.warning("FMP stock-screener returned %d", resp.status_code)
            return _universe_cache[1] if _universe_cache else []
        data = resp.json()
    except Exception as e:
        logger.warning("FMP stock-screener error: %s", e)
        return _universe_cache[1] if _universe_cache else []

    if not isinstance(data, list):
        return _universe_cache[1] if _universe_cache else []

    symbols: list[str] = []
    for row in data:
        sym = row.get("symbol") if isinstance(row, dict) else None
        if not sym or not isinstance(sym, str):
            continue
        # Skip non-common-stock instruments that FMP sometimes returns
        if "." in sym or "-" in sym:
            continue
        symbols.append(sym.upper())

    symbols = sorted(set(symbols))
    _universe_cache = (now, symbols)
    logger.info("FMP liquid universe refreshed: %d symbols", len(symbols))
    return symbols


def get_stock_grade(symbol: str) -> list[dict]:
    """Get analyst ratings/grades for a symbol."""
    cache_key = f"fmp_grade_{symbol}"
    data = _get(
        f"/grade/{symbol}",
        params={"limit": 10},
        cache_key=cache_key,
    )
    return data or []


def get_company_profile(symbol: str) -> dict:
    """Get company profile (sector, industry, name, beta) for a symbol."""
    cache_key = f"fmp_profile_{symbol}"
    data = _get(f"/profile/{symbol}", cache_key=cache_key, cache_ttl=24 * 60 * 60)
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return {}


def get_income_statement(symbol: str, period: str = "annual", limit: int = 10) -> list[dict]:
    """Income statement history (Starter+ required)."""
    cache_key = f"fmp_income_{symbol}_{period}_{limit}"
    data = _get(
        f"/income-statement/{symbol}",
        params={"period": period, "limit": limit},
        cache_key=cache_key,
        cache_ttl=24 * 60 * 60,
    )
    return data if isinstance(data, list) else []


def get_balance_sheet(symbol: str, period: str = "annual", limit: int = 10) -> list[dict]:
    """Balance sheet history (Starter+ required)."""
    cache_key = f"fmp_bs_{symbol}_{period}_{limit}"
    data = _get(
        f"/balance-sheet-statement/{symbol}",
        params={"period": period, "limit": limit},
        cache_key=cache_key,
        cache_ttl=24 * 60 * 60,
    )
    return data if isinstance(data, list) else []


def get_cash_flow(symbol: str, period: str = "annual", limit: int = 10) -> list[dict]:
    """Cash flow statement history (Starter+ required)."""
    cache_key = f"fmp_cf_{symbol}_{period}_{limit}"
    data = _get(
        f"/cash-flow-statement/{symbol}",
        params={"period": period, "limit": limit},
        cache_key=cache_key,
        cache_ttl=24 * 60 * 60,
    )
    return data if isinstance(data, list) else []


def get_key_metrics_ttm(symbol: str) -> dict:
    """TTM key metrics: P/E, EV/Sales, dividend yield, etc. (Starter+ required)."""
    cache_key = f"fmp_km_ttm_{symbol}"
    data = _get(
        f"/key-metrics-ttm/{symbol}",
        cache_key=cache_key,
        cache_ttl=60 * 60,
    )
    if isinstance(data, list) and data:
        return data[0]
    return {}


def get_enterprise_values(symbol: str, period: str = "annual", limit: int = 10) -> list[dict]:
    """Enterprise value history with market cap and shares outstanding."""
    cache_key = f"fmp_ev_{symbol}_{period}_{limit}"
    data = _get(
        f"/enterprise-values/{symbol}",
        params={"period": period, "limit": limit},
        cache_key=cache_key,
        cache_ttl=24 * 60 * 60,
    )
    return data if isinstance(data, list) else []


def get_quote(symbol: str) -> dict:
    """Real-time quote (works on free tier)."""
    cache_key = f"fmp_quote_{symbol}"
    data = _get(
        f"/quote/{symbol}",
        cache_key=cache_key,
        cache_ttl=60,
    )
    if isinstance(data, list) and data:
        return data[0]
    return {}
