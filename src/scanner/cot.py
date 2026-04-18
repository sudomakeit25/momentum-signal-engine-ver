"""Commitment of Traders (COT) data from CFTC Socrata public API.

Weekly report covering futures contracts. We surface the two headline
groups most retail traders care about — non-commercial (large specs)
and commercial hedgers — and derive net positions, week-over-week
change, and a 3-year percentile rank so you can see when positioning
is at an extreme.

No API key required. Free, rate limits are generous.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import requests

logger = logging.getLogger("mse.cot")


# Curated contracts. The `market_and_exchange_names` field from CFTC is
# verbose, so we use startswith match on a stable short code.
CONTRACTS: dict[str, dict] = {
    "gold": {"label": "Gold", "match": "GOLD - COMMODITY EXCHANGE INC."},
    "silver": {"label": "Silver", "match": "SILVER - COMMODITY EXCHANGE INC."},
    "wti": {"label": "WTI Crude Oil", "match": "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE"},
    "wti_nymex": {"label": "WTI Crude (NYMEX)", "match": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE"},
    "natgas": {"label": "Natural Gas", "match": "NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE"},
    "copper": {"label": "Copper", "match": "COPPER - COMMODITY EXCHANGE INC."},
    "corn": {"label": "Corn", "match": "CORN - CHICAGO BOARD OF TRADE"},
    "wheat": {"label": "Wheat", "match": "WHEAT-SRW - CHICAGO BOARD OF TRADE"},
    "soybeans": {"label": "Soybeans", "match": "SOYBEANS - CHICAGO BOARD OF TRADE"},
    "sp500": {"label": "S&P 500 E-mini", "match": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE"},
    "nasdaq": {"label": "Nasdaq-100 E-mini", "match": "NASDAQ-100 E-MINI - CHICAGO MERCANTILE EXCHANGE"},
    "dow": {"label": "Dow E-mini", "match": "E-MINI S&P MIDCAP 400 - CHICAGO MERCANTILE EXCHANGE"},
    "vix": {"label": "VIX Futures", "match": "VIX FUTURES - CBOE FUTURES EXCHANGE"},
    "eurusd": {"label": "EUR/USD", "match": "EURO FX - CHICAGO MERCANTILE EXCHANGE"},
    "gbpusd": {"label": "GBP/USD", "match": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"},
    "jpy": {"label": "Japanese Yen", "match": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE"},
    "audusd": {"label": "AUD/USD", "match": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE"},
    "cadusd": {"label": "CAD/USD", "match": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE"},
    "bitcoin": {"label": "Bitcoin Futures", "match": "BITCOIN - CHICAGO MERCANTILE EXCHANGE"},
    "ten_year": {"label": "10-Year T-Note", "match": "UST 10Y NOTE - CHICAGO BOARD OF TRADE"},
    "two_year": {"label": "2-Year T-Note", "match": "UST 2Y NOTE - CHICAGO BOARD OF TRADE"},
}

_CFTC_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
_cache: dict[str, tuple[float, dict]] = {}
_TTL = 12 * 60 * 60  # 12 hours — CFTC releases weekly (Friday PM)


def list_contracts() -> list[dict]:
    return [{"key": k, "label": v["label"]} for k, v in CONTRACTS.items()]


def get_cot(contract_key: str, years: int = 3) -> dict:
    """Return COT time series + current snapshot for a contract."""
    if contract_key not in CONTRACTS:
        return {"error": f"unknown contract '{contract_key}'", "available": list(CONTRACTS.keys())}

    cache_key = f"{contract_key}_{years}"
    now = time.time()
    if cache_key in _cache and now - _cache[cache_key][0] < _TTL:
        return _cache[cache_key][1]

    match = CONTRACTS[contract_key]["match"]
    start = (datetime.utcnow() - timedelta(days=years * 365 + 30)).strftime("%Y-%m-%dT00:00:00")
    params = {
        "$where": f"market_and_exchange_names like '{match}%' and report_date_as_yyyy_mm_dd >= '{start}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": 300,
    }

    try:
        resp = requests.get(_CFTC_URL, params=params, timeout=30)
        if resp.status_code != 200:
            return {"error": f"CFTC API returned {resp.status_code}"}
        rows = resp.json()
    except Exception as e:
        return {"error": f"fetch failed: {e}"}

    if not rows:
        return {"error": "no data for that contract"}

    # Normalize and chronologically sort
    series = []
    for r in rows:
        try:
            series.append({
                "date": (r.get("report_date_as_yyyy_mm_dd") or "")[:10],
                "open_interest": int(float(r.get("open_interest_all", 0) or 0)),
                "noncomm_long": int(float(r.get("noncomm_positions_long_all", 0) or 0)),
                "noncomm_short": int(float(r.get("noncomm_positions_short_all", 0) or 0)),
                "comm_long": int(float(r.get("comm_positions_long_all", 0) or 0)),
                "comm_short": int(float(r.get("comm_positions_short_all", 0) or 0)),
            })
        except (TypeError, ValueError):
            continue
    series.sort(key=lambda r: r["date"])

    for r in series:
        r["noncomm_net"] = r["noncomm_long"] - r["noncomm_short"]
        r["comm_net"] = r["comm_long"] - r["comm_short"]

    if not series:
        return {"error": "no usable rows"}

    latest = series[-1]
    prev = series[-2] if len(series) >= 2 else latest
    noncomm_nets = [r["noncomm_net"] for r in series]
    comm_nets = [r["comm_net"] for r in series]

    def _percentile(value: float, pool: list[float]) -> float:
        if not pool:
            return 50.0
        sorted_pool = sorted(pool)
        # Rank as fraction of values <= value
        rank = sum(1 for v in sorted_pool if v <= value)
        return round(rank / len(sorted_pool) * 100, 1)

    snapshot = {
        "report_date": latest["date"],
        "open_interest": latest["open_interest"],
        "noncomm_net": latest["noncomm_net"],
        "noncomm_net_change": latest["noncomm_net"] - prev["noncomm_net"],
        "noncomm_percentile_3y": _percentile(latest["noncomm_net"], noncomm_nets),
        "comm_net": latest["comm_net"],
        "comm_net_change": latest["comm_net"] - prev["comm_net"],
        "comm_percentile_3y": _percentile(latest["comm_net"], comm_nets),
        "noncomm_bias": "long" if latest["noncomm_net"] > 0 else "short",
        "comm_bias": "long" if latest["comm_net"] > 0 else "short",
    }

    bundle = {
        "contract": contract_key,
        "label": CONTRACTS[contract_key]["label"],
        "snapshot": snapshot,
        "series": series,
    }
    _cache[cache_key] = (now, bundle)
    return bundle
