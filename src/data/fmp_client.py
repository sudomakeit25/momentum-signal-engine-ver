"""Financial Modeling Prep (FMP) API client.

Free tier: 250 calls/day. Provides earnings calendar, EPS surprises,
analyst estimates, and insider trading data.

API versions. FMP retired /api/v3/ on 2025-08-31: those routes return 403
for every key except legacy subscriptions. The earnings calendar and the
company screener here use the current /stable/ API. The remaining functions
still call v3 and only work with a legacy key; `status()` shows which calls
are being refused so that is visible instead of silently empty.
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
_BASE = "https://financialmodelingprep.com/api/v3"      # legacy keys only
_STABLE = "https://financialmodelingprep.com/stable"

# Last outcome per endpoint, for status(): {endpoint: {ok, status, message, rows, at}}
_outcomes: dict[str, dict] = {}


def _record(endpoint: str, status_code: int, body, ok: bool) -> None:
    """Remember what FMP last answered for an endpoint. FMP explains refusals
    in an "Error Message" field (wrong plan, legacy-only, bad key)."""
    message = ""
    rows = 0
    if isinstance(body, dict):
        message = str(body.get("Error Message") or body.get("message") or "")
    elif isinstance(body, list):
        rows = len(body)
    elif isinstance(body, str):
        message = body
    key = settings.fmp_api_key or ""
    if key:
        message = message.replace(key, "***")
    _outcomes[endpoint] = {
        "ok": ok,
        "status": status_code,
        "message": message[:300],
        "rows": rows,
        "at": datetime.now().isoformat(timespec="seconds"),
    }


def status() -> dict:
    """What FMP last answered, per endpoint. Contains no secrets."""
    return {"configured": bool(settings.fmp_api_key), "endpoints": dict(_outcomes)}


def _request(base: str, endpoint: str, params: dict | None, timeout: int = 15):
    """One GET to FMP. Returns parsed JSON on HTTP 200, else None. Always
    records the outcome."""
    query = dict(params or {})
    query["apikey"] = settings.fmp_api_key
    try:
        resp = requests.get(f"{base}{endpoint}", params=query, timeout=timeout)
    except Exception as e:
        logger.warning("FMP error for %s: %s", endpoint, e)
        _record(endpoint, 0, f"request failed: {type(e).__name__}", ok=False)
        return None
    try:
        body = resp.json()
    except Exception:
        body = (resp.text or "")[:300]
    if resp.status_code != 200:
        _record(endpoint, resp.status_code, body, ok=False)
        logger.warning(
            "FMP %s returned %d: %s", endpoint, resp.status_code,
            _outcomes[endpoint]["message"] or "(no message)",
        )
        return None
    # FMP sometimes answers 200 with an error object instead of data
    if isinstance(body, dict) and body.get("Error Message"):
        _record(endpoint, resp.status_code, body, ok=False)
        logger.warning("FMP %s refused: %s", endpoint, _outcomes[endpoint]["message"])
        return None
    _record(endpoint, resp.status_code, body, ok=True)
    return body


def _get_stable(endpoint: str, params: dict | None = None, cache_key: str | None = None,
                timeout: int = 15) -> list | dict | None:
    """Rate-limited, cached GET against the current /stable/ API."""
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
    data = _request(_STABLE, endpoint, params, timeout=timeout)
    if cache_key and data:
        _cache.set(cache_key, data)
    return data

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

    data = _request(_BASE, endpoint, params)
    if cache_key and data:
        _cache.set(cache_key, data)
    return data


def _normalize_earnings(item) -> dict | None:
    """One calendar row in the shape the rest of the app reads.

    The stable API renamed the actuals (epsActual, revenueActual) and dropped
    the bmo/amc `time` field; the old names are accepted too, so a legacy
    response still parses.
    """
    if not isinstance(item, dict):
        return None
    symbol = item.get("symbol")
    date = item.get("date")
    if not symbol or not date or not isinstance(symbol, str):
        return None
    def first(*names):
        for name in names:
            if item.get(name) is not None:
                return item[name]
        return None
    return {
        "symbol": symbol.upper(),
        "date": str(date)[:10],
        "eps": first("epsActual", "eps"),
        "epsEstimated": first("epsEstimated", "epsEstimate"),
        "revenue": first("revenueActual", "revenue"),
        "revenueEstimated": first("revenueEstimated", "revenueEstimate"),
        "time": str(item.get("time") or ""),
    }


def get_earnings_calendar(days_ahead: int = 14) -> list[dict]:
    """Upcoming earnings for the next N days, market-wide. Returns [] when the
    calendar could not be read (callers treat an empty calendar as unknown)."""
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    cache_key = f"fmp_stable_earnings_cal_{today}_{end}"

    data = _get_stable(
        "/earnings-calendar",
        params={"from": today, "to": end},
        cache_key=cache_key,
    )
    if not isinstance(data, list):
        return []
    rows = [r for r in (_normalize_earnings(x) for x in data) if r is not None]
    return rows


# symbol -> day on which FMP refused it (free plan covers a limited symbol
# list). Remembered for the day so refusals do not eat the daily call budget.
_symbol_refused: dict[str, str] = {}


def get_symbol_next_earnings(symbol: str, today: str | None = None) -> tuple[bool, str | None]:
    """(known, next earnings date) for one symbol.

    known is False when FMP could not answer for this symbol: no key, rate
    limit, network error, or a plan that does not cover the symbol. The date
    is the earliest not-yet-reported earnings date from `today` on, or None.
    `today` defaults to the New York date: the host's clock is UTC, which is
    already tomorrow from 7 PM New York time.
    """
    symbol = symbol.upper()
    if today is None:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    if _symbol_refused.get(symbol) == today:
        return False, None
    data = _get_stable(
        "/earnings",
        params={"symbol": symbol, "limit": 5},
        cache_key=f"fmp_stable_symbol_earnings_{symbol}_{today}",
    )
    if not isinstance(data, list):
        last = _outcomes.get("/earnings", {})
        if last.get("status") in (401, 402, 403):
            _symbol_refused[symbol] = today
        return False, None
    upcoming = sorted(
        str(r.get("date"))[:10] for r in data
        if isinstance(r, dict) and r.get("date") and r.get("epsActual") is None
        and str(r.get("date"))[:10] >= today
    )
    return True, (upcoming[0] if upcoming else None)


_SCREEN_PAGE = 1000
_SCREEN_MAX_PAGES = 10


def screen_companies(filters: dict, max_rows: int = 10_000) -> list[dict] | None:
    """Rows from the stable company screener, or None if it could not be read.

    Pages through results (the screener caps a single response) and stops
    when a page adds nothing new, so a plan that ignores `page` cannot loop.
    """
    if not settings.fmp_api_key:
        return None
    rows: list[dict] = []
    seen: set[str] = set()
    for page in range(_SCREEN_MAX_PAGES):
        if not _limiter.try_acquire():
            logger.warning("FMP rate limit reached during screener paging")
            return rows or None
        params = {**filters, "limit": min(_SCREEN_PAGE, max_rows), "page": page}
        data = _request(_STABLE, "/company-screener", params, timeout=30)
        if not isinstance(data, list):
            return rows or None
        fresh = [r for r in data if isinstance(r, dict) and r.get("symbol") not in seen]
        for r in fresh:
            seen.add(r.get("symbol"))
        rows.extend(fresh)
        if not fresh or len(data) < params["limit"] or len(rows) >= max_rows:
            break
    return rows[:max_rows]


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

    # One request per exchange: the stable screener documents a single
    # exchange per call, where v3 took a comma-separated list.
    data: list[dict] = []
    for exchange in ("NYSE", "NASDAQ", "AMEX"):
        rows = screen_companies({
            "marketCapMoreThan": market_cap_min,
            "volumeMoreThan": volume_min,
            "priceMoreThan": price_min,
            "priceLowerThan": price_max,
            "isActivelyTrading": "true",
            "isEtf": "false",
            "isFund": "false",
            "exchange": exchange,
        })
        if rows:
            data.extend(rows)

    if not data:
        # Refused or empty: keep whatever universe we had (callers fall back
        # to the hardcoded list when this is empty).
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


def get_symbol_earnings(symbol: str, limit: int = 12) -> list[dict]:
    """Historical + upcoming earnings dates for a symbol."""
    cache_key = f"fmp_earn_{symbol}_{limit}"
    data = _get(
        f"/historical/earning_calendar/{symbol}",
        params={"limit": limit},
        cache_key=cache_key,
        cache_ttl=12 * 60 * 60,
    )
    return data if isinstance(data, list) else []


def get_symbol_dividends(symbol: str) -> list[dict]:
    """Dividend history for a symbol."""
    cache_key = f"fmp_div_{symbol}"
    data = _get(
        f"/historical-price-full/stock_dividend/{symbol}",
        cache_key=cache_key,
        cache_ttl=24 * 60 * 60,
    )
    if isinstance(data, dict):
        return data.get("historical") or []
    return []


def get_earnings_transcript(symbol: str, quarter: int, year: int) -> dict:
    """Fetch a specific quarter's earnings call transcript."""
    cache_key = f"fmp_trans_{symbol}_{year}_{quarter}"
    data = _get(
        f"/earning_call_transcript/{symbol}",
        params={"quarter": quarter, "year": year},
        cache_key=cache_key,
        cache_ttl=30 * 24 * 60 * 60,
    )
    if isinstance(data, list) and data:
        return data[0]
    return {}


def list_transcripts(symbol: str) -> list[dict]:
    """List available transcripts (quarter / year) for a symbol."""
    cache_key = f"fmp_translist_{symbol}"
    data = _get(
        f"/earning_call_transcript/{symbol}",
        cache_key=cache_key,
        cache_ttl=24 * 60 * 60,
    )
    if not isinstance(data, list):
        return []
    seen: set[tuple[int, int]] = set()
    out = []
    for row in data:
        q = row.get("quarter")
        y = row.get("year")
        if q and y and (q, y) not in seen:
            seen.add((q, y))
            out.append({
                "quarter": q,
                "year": y,
                "date": row.get("date", "")[:10],
            })
    out.sort(key=lambda r: (r["year"], r["quarter"]), reverse=True)
    return out[:8]


def get_symbol_splits(symbol: str) -> list[dict]:
    """Stock split history for a symbol."""
    cache_key = f"fmp_split_{symbol}"
    data = _get(
        f"/historical-price-full/stock_split/{symbol}",
        cache_key=cache_key,
        cache_ttl=24 * 60 * 60,
    )
    if isinstance(data, dict):
        return data.get("historical") or []
    return []


def get_historical_prices(symbol: str, days: int = 260):
    """Fetch daily OHLCV for any ticker FMP covers — returns a pandas DataFrame
    matching the shape Alpaca client produces (index=date, columns open/high/
    low/close/volume). Used as the fallback price source for international
    tickers Alpaca does not cover.
    """
    import pandas as pd
    from datetime import datetime, timedelta

    cache_key = f"fmp_hist_{symbol}_{days}"
    data = _get(
        f"/historical-price-full/{symbol}",
        params={
            "from": (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "to": datetime.utcnow().strftime("%Y-%m-%d"),
        },
        cache_key=cache_key,
        cache_ttl=60 * 60,
    )
    if not data or not isinstance(data, dict):
        return pd.DataFrame()
    rows = data.get("historical") or []
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([
        {
            "open": float(r.get("open", 0) or 0),
            "high": float(r.get("high", 0) or 0),
            "low": float(r.get("low", 0) or 0),
            "close": float(r.get("close", 0) or 0),
            "volume": int(r.get("volume", 0) or 0),
            "_date": r.get("date"),
        }
        for r in rows
    ])
    df.index = pd.to_datetime(df["_date"])
    df = df.drop(columns=["_date"]).sort_index()
    return df
