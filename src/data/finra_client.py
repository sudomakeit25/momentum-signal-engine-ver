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
# Bi-monthly consolidated short interest (shares short, days-to-cover).
# Different dataset from the daily RegSHO short *volume* above — this is
# the real "short interest" feed, settled twice a month with ~2-week lag.
_FINRA_SI_API = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
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


def _candidate_settlement_dates(lookback_months: int = 3) -> list[str]:
    """Short interest settles on the 15th and the last business day of each
    month. Generate candidate settlement dates (newest first) so we can
    probe for the most recent published cycle without hardcoding it.
    """
    today = datetime.now()
    candidates: list[datetime] = []

    def _prev_business_day(d: datetime) -> datetime:
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d

    year, month = today.year, today.month
    for _ in range(lookback_months + 1):
        # Mid-month settlement (15th, rolled back if weekend)
        mid = _prev_business_day(datetime(year, month, 15))
        candidates.append(mid)
        # End-of-month settlement (last business day)
        if month == 12:
            first_next = datetime(year + 1, 1, 1)
        else:
            first_next = datetime(year, month + 1, 1)
        eom = _prev_business_day(first_next - timedelta(days=1))
        candidates.append(eom)
        # Step back a month
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    # Only dates in the past, newest first, de-duplicated
    seen: set[str] = set()
    out: list[str] = []
    for d in sorted(candidates, reverse=True):
        s = d.strftime("%Y-%m-%d")
        if d <= today and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _fetch_short_interest_cycle(date_str: str) -> dict[str, dict]:
    """Fetch the full consolidated short-interest cycle for one settlement
    date. Returns {symbol -> {shares_short, prev_shares_short,
    avg_daily_volume, days_to_cover, change_pct}}. Empty if not published.
    """
    cache_key = f"finra_si_{date_str}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    all_rows = []
    offset = 0
    limit = 5000
    while True:
        payload = {
            "fields": [
                "symbolCode",
                "currentShortPositionQuantity",
                "previousShortPositionQuantity",
                "averageDailyVolumeQuantity",
                "daysToCoverQuantity",
                "changePercent",
                "settlementDate",
            ],
            "compareFilters": [
                {"fieldName": "settlementDate", "fieldValue": date_str, "compareType": "EQUAL"}
            ],
            "limit": limit,
            "offset": offset,
        }
        try:
            resp = requests.post(_FINRA_SI_API, json=payload, headers=_HEADERS, timeout=30)
            if resp.status_code != 200:
                logger.debug("FINRA SI API returned %d for %s", resp.status_code, date_str)
                break
            rows = resp.json()
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < limit:
                break
            offset += limit
        except Exception as e:
            logger.warning("FINRA SI API error for %s: %s", date_str, e)
            break

    result: dict[str, dict] = {}
    for row in all_rows:
        symbol = (row.get("symbolCode") or "").upper()
        if not symbol:
            continue
        # Last row wins if a symbol appears twice (revisions); fine here.
        result[symbol] = {
            "shares_short": int(row.get("currentShortPositionQuantity", 0) or 0),
            "prev_shares_short": int(row.get("previousShortPositionQuantity", 0) or 0),
            "avg_daily_volume": int(row.get("averageDailyVolumeQuantity", 0) or 0),
            "days_to_cover": float(row.get("daysToCoverQuantity", 0) or 0),
            "change_pct": float(row.get("changePercent", 0) or 0),
            "settlement_date": date_str,
        }

    if result:
        _cache.set(cache_key, result)
        logger.info("FINRA SI: fetched %d symbols for %s", len(result), date_str)
    return result


def get_short_interest() -> dict[str, dict]:
    """Return the most recent published consolidated short-interest cycle.

    Probes candidate settlement dates newest-first and returns the first
    cycle that has data. Each value: {shares_short, prev_shares_short,
    avg_daily_volume, days_to_cover, change_pct, settlement_date}.
    """
    cache_key = "finra_si_latest"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    for date_str in _candidate_settlement_dates():
        cycle = _fetch_short_interest_cycle(date_str)
        if cycle:
            _cache.set(cache_key, cycle)
            return cycle
    return {}


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
