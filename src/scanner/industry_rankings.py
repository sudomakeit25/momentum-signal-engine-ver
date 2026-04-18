"""Industry rankings — list companies in an industry with Z, F, M scores.

Uses the FMP stock-screener to get all tickers in an industry, then
parallel-fetches profile + two years of income / balance / cash-flow to
compute Altman Z, Piotroski F, and Beneish M. Caches aggressively (24h)
so the first view of an industry is slow but subsequent views are fast.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.settings import settings
from src.data import fmp_client
from src.scanner.instrument_fundamentals import (
    _altman_z_score,
    _beneish_m_score,
    _piotroski_f_score,
    _safe_float,
)

logger = logging.getLogger("mse.industry_rankings")

# Industry slug → FMP industry string mapping.
_INDUSTRY_ALIASES: dict[str, str] = {
    "aerospace-defense": "Aerospace & Defense",
    "semiconductors": "Semiconductors",
    "software-application": "Software - Application",
    "software-infrastructure": "Software - Infrastructure",
    "oil-gas-eandp": "Oil & Gas E&P",
    "biotechnology": "Biotechnology",
    "banks-diversified": "Banks - Diversified",
    "internet-content": "Internet Content & Information",
    "drug-manufacturers-general": "Drug Manufacturers - General",
    "consumer-electronics": "Consumer Electronics",
    "auto-manufacturers": "Auto Manufacturers",
}

_MAX_TICKERS = 30  # cap per industry so FMP rate limits are manageable
_INDUSTRY_CACHE: dict[str, tuple[float, dict]] = {}
_INDUSTRY_TTL = 24 * 60 * 60  # 24 hours


def list_known_industries() -> list[dict]:
    return [{"slug": k, "label": v} for k, v in _INDUSTRY_ALIASES.items()]


def _value_generation_label(f: int | None, z: float | None, m: float | None) -> str:
    if f is None and z is None:
        return "Unknown"
    strong = (f or 0) >= 7
    safe = (z or 0) > 2.99
    clean = m is None or m <= -1.78
    if strong and safe and clean:
        return "Resilient"
    if strong and clean:
        return "Robust"
    if (f or 0) >= 4 and (m is None or clean):
        return "Steady"
    return "Weak"


def _company_scorecard(symbol: str) -> dict | None:
    """Fetch the three statements + profile and compute Z/F/M for one symbol."""
    try:
        profile = fmp_client.get_company_profile(symbol)
        income = fmp_client.get_income_statement(symbol, limit=3)
        balance = fmp_client.get_balance_sheet(symbol, limit=3)
        cash_flow = fmp_client.get_cash_flow(symbol, limit=3)
        if not income or not balance:
            return None

        cur_i = income[0]
        prev_i = income[1] if len(income) > 1 else {}
        cur_b = balance[0]
        prev_b = balance[1] if len(balance) > 1 else {}
        cur_cf = cash_flow[0] if cash_flow else {}

        market_cap = _safe_float(profile.get("mktCap"))
        z = _altman_z_score(
            {"revenue": _safe_float(cur_i.get("revenue")),
             "operatingIncome": _safe_float(cur_i.get("operatingIncome")),
             "netIncome": _safe_float(cur_i.get("netIncome"))},
            cur_b,
            market_cap,
        )
        f = _piotroski_f_score(cur_i, prev_i, cur_b, prev_b, cur_cf) if prev_i and prev_b and cur_cf else None
        m = _beneish_m_score(cur_i, prev_i, cur_b, prev_b, cur_cf) if prev_i and prev_b and cur_cf else None

        # Fair value via EV/Sales historical multiple
        revenue = _safe_float(cur_i.get("revenue"))
        ev_list = fmp_client.get_enterprise_values(symbol, limit=5)
        fair_pct = None
        if ev_list and revenue > 0:
            ratios = []
            for ev in ev_list:
                s = _safe_float(ev.get("numberOfShares"))
                rev_for = _safe_float(cur_i.get("revenue"))
                evv = _safe_float(ev.get("enterpriseValue"))
                if rev_for > 0 and evv > 0:
                    ratios.append(evv / rev_for)
            if ratios:
                avg_ratio = sum(ratios) / len(ratios)
                latest_shares = _safe_float(ev_list[0].get("numberOfShares"))
                if latest_shares > 0:
                    fair_value = (avg_ratio * revenue) / latest_shares
                    price = _safe_float(profile.get("price"))
                    if price > 0 and fair_value > 0:
                        fair_pct = round((fair_value - price) / price * 100, 2)

        return {
            "symbol": symbol,
            "name": profile.get("companyName") or symbol,
            "logo": profile.get("image") or "",
            "market_cap": market_cap,
            "country": profile.get("country") or "",
            "price": _safe_float(profile.get("price")),
            "fair_value_pct": fair_pct,
            "z_score": z,
            "f_score": f,
            "m_score": m,
            "value_generation": _value_generation_label(f, z, m),
        }
    except Exception as e:
        logger.debug("scorecard failed for %s: %s", symbol, e)
        return None


def get_industry_ranking(industry_slug: str, limit: int = _MAX_TICKERS) -> dict:
    """Return ranked companies in an industry with Z/F/M/Value-Gen scores."""
    industry = _INDUSTRY_ALIASES.get(industry_slug, industry_slug)
    cache_key = f"{industry_slug}:{limit}"
    now = time.time()
    if cache_key in _INDUSTRY_CACHE and now - _INDUSTRY_CACHE[cache_key][0] < _INDUSTRY_TTL:
        return _INDUSTRY_CACHE[cache_key][1]

    if not settings.fmp_api_key:
        return {"error": "FMP key not configured", "industry": industry, "companies": []}

    # Step 1: list tickers in this industry via FMP screener
    import requests
    params = {
        "industry": industry,
        "limit": 500,
        "apikey": settings.fmp_api_key,
    }
    try:
        resp = requests.get(
            "https://financialmodelingprep.com/api/v3/stock-screener",
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            return {"error": f"FMP screener {resp.status_code}", "industry": industry, "companies": []}
        data = resp.json()
    except Exception as e:
        return {"error": f"screener failed: {e}", "industry": industry, "companies": []}

    if not isinstance(data, list) or not data:
        return {"industry": industry, "companies": [], "country_weights": {}}

    # Sort by market cap, take top N
    sorted_rows = sorted(
        data, key=lambda r: _safe_float(r.get("marketCap")), reverse=True
    )[:limit]
    symbols = [r["symbol"] for r in sorted_rows if r.get("symbol")]

    # Step 2: parallel fetch scorecards
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_company_scorecard, s): s for s in symbols}
        for fut in as_completed(futures):
            r = fut.result()
            if r is not None:
                results.append(r)

    # Step 3: aggregate country weights
    country_weights: dict[str, float] = {}
    total_cap = sum(r.get("market_cap", 0) for r in results if r.get("market_cap"))
    if total_cap > 0:
        for r in results:
            c = r.get("country") or "Unknown"
            country_weights[c] = country_weights.get(c, 0.0) + r.get("market_cap", 0) / total_cap
        country_weights = {k: round(v, 4) for k, v in sorted(
            country_weights.items(), key=lambda kv: -kv[1]
        )}

    # Industry-level fair value average (median of fair_value_pct)
    fvs = [r["fair_value_pct"] for r in results if r.get("fair_value_pct") is not None]
    industry_fair_value_pct = None
    if fvs:
        fvs_sorted = sorted(fvs)
        mid = len(fvs_sorted) // 2
        industry_fair_value_pct = (
            fvs_sorted[mid]
            if len(fvs_sorted) % 2
            else (fvs_sorted[mid - 1] + fvs_sorted[mid]) / 2
        )

    # Sort results by market cap desc (default view)
    results.sort(key=lambda r: -(r.get("market_cap") or 0))

    bundle = {
        "industry": industry,
        "slug": industry_slug,
        "company_count": len(results),
        "country_weights": country_weights,
        "industry_fair_value_pct": (
            round(industry_fair_value_pct, 2) if industry_fair_value_pct is not None else None
        ),
        "companies": results,
    }
    _INDUSTRY_CACHE[cache_key] = (now, bundle)
    return bundle
