"""FINRA short sale volume data client.

Uses the FINRA API gateway to fetch RegSHO daily short volume data.
Free, no API key needed. Data is T+1 (one day delayed).
Short volume is a proxy for dark pool / off-exchange activity.
"""

import logging
from datetime import datetime, timedelta

import requests

from src.data.cache import Cache

logger = logging.getLogger("mse.finra")

_cache = Cache()
_FINRA_API = "https://api.finra.org/data/group/OTCMarket/name/regShoDaily"
_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


def _fetch_daily_report(date: datetime) -> dict[str, dict]:
    """Fetch FINRA short volume report for a given date.

    Returns dict mapping symbol -> {short_volume, short_exempt_volume, total_volume}.
    Aggregates across all reporting facilities.
    """
    date_str = date.strftime("%Y-%m-%d")
    cache_key = f"finra_daily_{date_str}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # FINRA API requires tradeReportDate as partition key
    # Fetch all symbols for this date (paginate with offset)
    all_rows = []
    offset = 0
    limit = 5000

    while True:
        payload = {
            "fields": [
                "securitiesInformationProcessorSymbolIdentifier",
                "shortParQuantity",
                "shortExemptParQuantity",
                "totalParQuantity",
            ],
            "compareFilters": [
                {
                    "fieldName": "tradeReportDate",
                    "fieldValue": date_str,
                    "compareType": "EQUAL",
                }
            ],
            "limit": limit,
            "offset": offset,
        }

        try:
            resp = requests.post(_FINRA_API, json=payload, headers=_HEADERS, timeout=30)
            if resp.status_code != 200:
                logger.debug("FINRA API returned %d for %s", resp.status_code, date_str)
                break
            rows = resp.json()
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < limit:
                break
            offset += limit
        except Exception as e:
            logger.warning("FINRA API error for %s: %s", date_str, e)
            break

    # Aggregate across reporting facilities per symbol
    result: dict[str, dict] = {}
    for row in all_rows:
        symbol = row.get("securitiesInformationProcessorSymbolIdentifier", "")
        if not symbol:
            continue
        short_vol = int(row.get("shortParQuantity", 0))
        short_exempt = int(row.get("shortExemptParQuantity", 0))
        total_vol = int(row.get("totalParQuantity", 0))

        if symbol in result:
            result[symbol]["short_volume"] += short_vol
            result[symbol]["short_exempt_volume"] += short_exempt
            result[symbol]["total_volume"] += total_vol
        else:
            result[symbol] = {
                "short_volume": short_vol,
                "short_exempt_volume": short_exempt,
                "total_volume": total_vol,
            }

    if result:
        _cache.set(cache_key, result)
        logger.info("FINRA: fetched %d symbols for %s", len(result), date_str)

    return result


def get_short_volume(symbol: str, days: int = 20) -> list[dict]:
    """Get daily short volume data for a symbol over the last N trading days."""
    cache_key = f"finra_short_{symbol}_{days}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    entries = []
    date = datetime.now()
    attempts = 0
    max_attempts = days * 2

    while len(entries) < days and attempts < max_attempts:
        date -= timedelta(days=1)
        attempts += 1

        if date.weekday() >= 5:
            continue

        report = _fetch_daily_report(date)
        sym_upper = symbol.upper()
        if sym_upper in report:
            data = report[sym_upper]
            total = data["total_volume"]
            short = data["short_volume"]
            entries.append({
                "date": date.isoformat(),
                "short_volume": short,
                "short_exempt_volume": data["short_exempt_volume"],
                "total_volume": total,
                "short_pct": round(short / total * 100, 2) if total > 0 else 0,
            })

    entries.reverse()
    if entries:
        _cache.set(cache_key, entries)
    return entries


def get_short_volume_batch(symbols: list[str], days: int = 20) -> dict[str, list[dict]]:
    """Get short volume data for multiple symbols efficiently.

    Fetches daily reports once and extracts data for all symbols.
    """
    cache_key = f"finra_batch_{len(symbols)}_{days}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    daily_reports = []
    date = datetime.now()
    attempts = 0
    max_attempts = days * 2

    while len(daily_reports) < days and attempts < max_attempts:
        date -= timedelta(days=1)
        attempts += 1
        if date.weekday() >= 5:
            continue

        report = _fetch_daily_report(date)
        if report:
            daily_reports.append((date, report))

    daily_reports.reverse()

    result = {}
    for symbol in symbols:
        sym_upper = symbol.upper()
        entries = []
        for report_date, report in daily_reports:
            if sym_upper in report:
                data = report[sym_upper]
                total = data["total_volume"]
                short = data["short_volume"]
                entries.append({
                    "date": report_date.isoformat(),
                    "short_volume": short,
                    "short_exempt_volume": data["short_exempt_volume"],
                    "total_volume": total,
                    "short_pct": round(short / total * 100, 2) if total > 0 else 0,
                })
        if entries:
            result[symbol] = entries

    if result:
        _cache.set(cache_key, result)
    return result
