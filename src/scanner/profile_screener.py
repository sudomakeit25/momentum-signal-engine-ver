"""Profile screener - sector universes + fundamentals via yfinance.

Ported from wash-sale-tracker. Filters a small curated universe (~30 tickers
per sector) on forward P/E, 6-month price momentum, revenue growth, and
market cap. Results are cached in-process for 30 min to keep Yahoo Finance
hits low. Sorted by forward P/E ascending (cheapest first).
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("mse.profile_screener")

_INFO_WORKERS = 8

SECTORS: dict[str, list[str]] = {
    "semiconductors": [
        "MU", "AMD", "NVDA", "AVGO", "INTC", "QCOM", "TSM", "MRVL", "TXN",
        "LRCX", "KLAC", "AMAT", "ON", "NXPI", "MCHP", "ADI", "SWKS", "STX",
        "WDC", "SNDK", "ARM", "SMCI", "CRDO", "ASML", "MPWR", "GFS", "UMC",
        "CEVA", "WOLF", "SLAB", "HIMX", "ACLS", "RMBS", "DIOD",
    ],
    "software": [
        "MSFT", "CRM", "ORCL", "ADBE", "NOW", "INTU", "SNOW", "DDOG", "NET",
        "ZS", "CRWD", "PANW", "WDAY", "TEAM", "MDB", "HUBS", "OKTA", "ZM",
        "PLTR", "GTLB", "PATH", "CFLT", "ESTC", "MNDY", "DOCN", "APP",
    ],
    "ai_infrastructure": [
        "NVDA", "AMD", "AVGO", "MRVL", "TSM", "SMCI", "ARM", "CRDO",
        "ANET", "VRT", "DELL", "HPE", "IONQ", "RGTI", "QUBT",
        "PLTR", "AI", "BBAI", "SOUN", "UPST",
    ],
    "space_defense": [
        "RKLB", "ASTS", "PL", "LUNR", "MNTS", "BKSY", "SPIR",
        "LMT", "RTX", "NOC", "BA", "GD", "LHX", "HII",
    ],
    "energy": [
        "XOM", "CVX", "COP", "SLB", "OXY", "DVN", "MPC", "PSX",
        "EOG", "HES", "VLO", "HAL", "KNTK", "TRGP", "WMB", "KMI",
        "FANG", "CEG", "VST", "NRG",
    ],
    "mega_cap": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
        "AVGO", "BRK-B", "LLY", "JPM", "V", "MA", "UNH", "HD",
        "PG", "COST", "NFLX", "CRM", "AMD",
    ],
    "healthcare": [
        "LLY", "UNH", "JNJ", "PFE", "ABBV", "MRK", "BMY", "AMGN",
        "TMO", "ABT", "DHR", "ISRG", "MDT", "GILD", "VRTX", "REGN",
        "CVS", "ELV", "HUM", "CI", "BSX", "SYK", "ZTS", "BIIB",
    ],
    "financials": [
        "JPM", "BAC", "GS", "MS", "WFC", "C", "SCHW", "BLK",
        "AXP", "COF", "ICE", "CME", "SPGI", "MMC", "V", "MA",
        "PNC", "USB", "TFC", "PGR", "ALL", "TRV", "MET", "AFL",
    ],
    "consumer": [
        "AMZN", "WMT", "COST", "HD", "LOW", "TGT", "NKE", "SBUX",
        "MCD", "DIS", "CMG", "LULU", "ROST", "TJX", "PG", "KO",
        "PEP", "CL", "MDLZ", "MNST", "EL", "KMB",
    ],
}

PROFILES: dict[str, dict] = {
    "like_mu": {
        "label": "Like MU (cheap semis)",
        "sector": "semiconductors",
        "max_fwd_pe": 15,
        "min_momentum_6m": None,
        "min_rev_growth": 20,
        "min_cap_billions": 5,
    },
    "ai_infrastructure": {
        "label": "AI infrastructure",
        "sector": "ai_infrastructure",
        "max_fwd_pe": None,
        "min_momentum_6m": None,
        "min_rev_growth": None,
        "min_cap_billions": 5,
    },
    "high_momentum": {
        "label": "High momentum",
        "sector": "semiconductors",
        "max_fwd_pe": None,
        "min_momentum_6m": 30,
        "min_rev_growth": None,
        "min_cap_billions": 10,
    },
    "space_defense": {
        "label": "Space & defense",
        "sector": "space_defense",
        "max_fwd_pe": None,
        "min_momentum_6m": None,
        "min_rev_growth": None,
        "min_cap_billions": None,
    },
    "energy": {
        "label": "Energy",
        "sector": "energy",
        "max_fwd_pe": 25,
        "min_momentum_6m": None,
        "min_rev_growth": None,
        "min_cap_billions": 5,
    },
    "mega_cap": {
        "label": "Mega-cap",
        "sector": "mega_cap",
        "max_fwd_pe": None,
        "min_momentum_6m": None,
        "min_rev_growth": None,
        "min_cap_billions": 100,
    },
    "software_saas": {
        "label": "Software / SaaS",
        "sector": "software",
        "max_fwd_pe": None,
        "min_momentum_6m": None,
        "min_rev_growth": 15,
        "min_cap_billions": 5,
    },
    "healthcare_value": {
        "label": "Healthcare value",
        "sector": "healthcare",
        "max_fwd_pe": 20,
        "min_momentum_6m": None,
        "min_rev_growth": None,
        "min_cap_billions": 20,
    },
    "financial_leaders": {
        "label": "Financial leaders",
        "sector": "financials",
        "max_fwd_pe": 15,
        "min_momentum_6m": None,
        "min_rev_growth": None,
        "min_cap_billions": 50,
    },
    "custom": {
        "label": "Custom",
        "sector": "semiconductors",
        "max_fwd_pe": None,
        "min_momentum_6m": None,
        "min_rev_growth": None,
        "min_cap_billions": None,
    },
}

_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 30 * 60  # 30 minutes


def list_profiles() -> list[dict]:
    """Return all profile presets with their default filter values."""
    return [{"key": k, **v} for k, v in PROFILES.items()]


def list_sectors() -> list[str]:
    """Return the available sector universe keys."""
    return list(SECTORS.keys())


# Sectors worth warming on every refresh cycle. Kept narrow to cap yfinance
# load — `semiconductors` also serves the `high_momentum` profile.
WARMUP_SECTORS: tuple[str, ...] = ("semiconductors", "ai_infrastructure", "mega_cap")


def warm_cache(sectors: tuple[str, ...] = WARMUP_SECTORS) -> int:
    """Prime the 30-min cache for the given sectors. Returns rows fetched."""
    total = 0
    for sec in sectors:
        tickers = SECTORS.get(sec)
        if not tickers:
            continue
        cache_key = f"{sec}:{','.join(sorted(tickers))}"
        now = time.time()
        if cache_key in _cache and now - _cache[cache_key][0] < _CACHE_TTL:
            continue  # still fresh
        try:
            rows = _fetch_all(tickers)
            _cache[cache_key] = (now, rows)
            total += len(rows)
            logger.info("warmed profile cache: sector=%s rows=%d", sec, len(rows))
        except Exception as e:
            logger.warning("warmup failed for %s: %s", sec, e)
    return total


def screen(
    sector: str = "semiconductors",
    max_fwd_pe: float | None = None,
    min_momentum_6m: float | None = None,
    min_rev_growth: float | None = None,
    min_cap: float | None = None,
    custom_tickers: str = "",
) -> list[dict]:
    """Screen a sector universe with optional fundamental/momentum filters.

    `min_cap` is the raw market cap (e.g. 5e9 for $5B). Returns a list of
    dicts sorted by forward P/E ascending.
    """
    if custom_tickers.strip():
        tickers = [t.strip().upper() for t in custom_tickers.split(",") if t.strip()]
    else:
        tickers = SECTORS.get(sector, SECTORS["semiconductors"])

    cache_key = f"{sector}:{','.join(sorted(tickers))}"
    now = time.time()
    if cache_key in _cache and now - _cache[cache_key][0] < _CACHE_TTL:
        rows = _cache[cache_key][1]
    else:
        rows = _fetch_all(tickers)
        _cache[cache_key] = (now, rows)

    filtered: list[dict] = []
    for r in rows:
        if max_fwd_pe is not None and (r["fwd_pe"] is None or r["fwd_pe"] <= 0 or r["fwd_pe"] > max_fwd_pe):
            continue
        if min_momentum_6m is not None and r["chg_6m"] < min_momentum_6m:
            continue
        if min_rev_growth is not None and r["rev_growth"] < min_rev_growth:
            continue
        if min_cap is not None and r["cap"] < min_cap:
            continue
        filtered.append(r)

    filtered.sort(key=lambda x: x["fwd_pe"] if x["fwd_pe"] and x["fwd_pe"] > 0 else 9999)
    return filtered


def _fetch_all(tickers: list[str]) -> list[dict]:
    import yfinance as yf

    try:
        hist = yf.download(
            " ".join(tickers),
            period="6mo",
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=True,
        )
    except Exception as e:
        logger.warning("yfinance batch download failed: %s", e)
        hist = None

    def _price_stats(t: str) -> tuple[float | None, float, float, float]:
        if hist is None or hist.empty:
            return None, 0.0, 0.0, 0.0
        try:
            series = None
            if "Close" in hist.columns.get_level_values(0):
                close_col = hist["Close"]
                if t in close_col.columns:
                    series = close_col[t].dropna()
                elif len(tickers) == 1:
                    series = (
                        close_col.iloc[:, 0].dropna()
                        if hasattr(close_col, "iloc")
                        else close_col.dropna()
                    )
            if series is None or len(series) < 2:
                return None, 0.0, 0.0, 0.0
            cur = float(series.iloc[-1])
            start = float(series.iloc[0])
            chg = (cur / start - 1) * 100 if start > 0 else 0.0
            return cur, chg, float(series.max()), float(series.min())
        except Exception:
            return None, 0.0, 0.0, 0.0

    def _fetch_one(t: str) -> dict | None:
        try:
            stock = yf.Ticker(t)
            info = stock.info or {}
            cur, chg, high_6m, low_6m = _price_stats(t)
            if cur is None:
                cur = info.get("currentPrice") or info.get("previousClose") or 0

            cap = info.get("marketCap", 0) or 0
            fwd_pe = info.get("forwardPE")
            trail_pe = info.get("trailingPE")
            rev_growth = info.get("revenueGrowth", 0) or 0
            name = (info.get("shortName") or t)[:35]
            sector_name = info.get("sector", "")
            industry = info.get("industry", "")

            return {
                "ticker": t,
                "name": name,
                "price": round(float(cur), 2),
                "cap": int(cap),
                "fwd_pe": round(float(fwd_pe), 2) if fwd_pe else None,
                "trail_pe": round(float(trail_pe), 2) if trail_pe else None,
                "chg_6m": round(chg, 2),
                "high_6m": round(high_6m, 2),
                "low_6m": round(low_6m, 2),
                "rev_growth": round(rev_growth * 100, 1),
                "sector": sector_name,
                "industry": industry,
            }
        except Exception as e:
            logger.debug("fetch failed for %s: %s", t, e)
            return None

    with ThreadPoolExecutor(max_workers=_INFO_WORKERS) as pool:
        rows = [r for r in pool.map(_fetch_one, tickers) if r is not None]
    return rows
