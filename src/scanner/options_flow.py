"""Options flow analysis - unusual activity and sentiment detection.

Analyzes options chain data from Polygon.io to detect:
- Unusual volume/OI ratios (smart money positioning)
- Put/call ratio shifts
- Large premium flow direction
"""

import logging
from datetime import datetime

from src.data.polygon_client import get_options_snapshot
from src.data.models import OptionsContract, OptionsFlowResult

logger = logging.getLogger("mse.options_flow")

# Thresholds
MIN_VOL_OI_RATIO = 3.0  # flag contracts where volume > 3x open interest
MIN_VOLUME = 100  # ignore low-volume noise
MIN_OI = 10  # ignore contracts with negligible open interest


def analyze_symbol(symbol: str) -> OptionsFlowResult | None:
    """Analyze options flow for a single symbol."""
    snapshot = get_options_snapshot(symbol)
    if not snapshot:
        return None

    contracts = _parse_contracts(symbol, snapshot)
    if not contracts:
        return None

    unusual = _detect_unusual(contracts)
    total_call_vol, total_put_vol = _compute_volumes(contracts)
    pc_ratio = _put_call_ratio(total_call_vol, total_put_vol)
    sentiment = _determine_sentiment(pc_ratio, unusual)
    alerts = _generate_alerts(symbol, unusual, pc_ratio, sentiment, total_call_vol, total_put_vol)

    return OptionsFlowResult(
        symbol=symbol,
        unusual_contracts=unusual[:20],  # top 20 most unusual
        put_call_ratio=pc_ratio,
        total_call_volume=total_call_vol,
        total_put_volume=total_put_vol,
        flow_sentiment=sentiment,
        alert_reasons=alerts,
    )


def _parse_contracts(symbol: str, snapshot: list[dict]) -> list[OptionsContract]:
    """Parse Polygon snapshot data into OptionsContract models."""
    contracts = []
    for item in snapshot:
        try:
            details = item.get("details", {})
            day = item.get("day", {})
            greeks = item.get("greeks", {})

            contract_type = details.get("contract_type", "").lower()
            if contract_type not in ("call", "put"):
                continue

            volume = day.get("volume", 0) or 0
            oi = day.get("open_interest", 0) or item.get("open_interest", 0) or 0

            if volume < MIN_VOLUME:
                continue

            vol_oi = volume / oi if oi > 0 else 0
            exp_str = details.get("expiration_date", "")
            if not exp_str:
                continue

            contracts.append(OptionsContract(
                symbol=symbol,
                expiration=datetime.strptime(exp_str, "%Y-%m-%d"),
                strike=details.get("strike_price", 0),
                contract_type=contract_type,
                volume=volume,
                open_interest=oi,
                vol_oi_ratio=round(vol_oi, 2),
                implied_volatility=greeks.get("implied_volatility"),
                last_price=day.get("close") or day.get("last_price"),
            ))
        except Exception:
            continue

    return contracts


def _detect_unusual(contracts: list[OptionsContract]) -> list[OptionsContract]:
    """Find contracts with unusual volume relative to open interest."""
    unusual = [
        c for c in contracts
        if c.vol_oi_ratio >= MIN_VOL_OI_RATIO and c.open_interest >= MIN_OI
    ]
    unusual.sort(key=lambda c: c.vol_oi_ratio, reverse=True)
    return unusual


def _compute_volumes(contracts: list[OptionsContract]) -> tuple[int, int]:
    """Compute total call and put volume."""
    call_vol = sum(c.volume for c in contracts if c.contract_type == "call")
    put_vol = sum(c.volume for c in contracts if c.contract_type == "put")
    return call_vol, put_vol


def _put_call_ratio(call_vol: int, put_vol: int) -> float:
    """Calculate put/call ratio."""
    if call_vol == 0:
        return 99.0 if put_vol > 0 else 0.0
    return round(put_vol / call_vol, 3)


def _determine_sentiment(pc_ratio: float, unusual: list[OptionsContract]) -> str:
    """Determine overall flow sentiment."""
    # Count unusual calls vs puts
    unusual_calls = sum(1 for c in unusual if c.contract_type == "call")
    unusual_puts = sum(1 for c in unusual if c.contract_type == "put")

    # Combine PC ratio signal with unusual activity
    if pc_ratio < 0.5 or unusual_calls > unusual_puts * 2:
        return "bullish"
    elif pc_ratio > 1.5 or unusual_puts > unusual_calls * 2:
        return "bearish"
    return "neutral"


def _generate_alerts(
    symbol: str,
    unusual: list[OptionsContract],
    pc_ratio: float,
    sentiment: str,
    call_vol: int,
    put_vol: int,
) -> list[str]:
    """Generate alert reasons for notable options activity."""
    alerts = []

    if len(unusual) >= 5:
        call_count = sum(1 for c in unusual if c.contract_type == "call")
        put_count = sum(1 for c in unusual if c.contract_type == "put")
        alerts.append(
            f"{symbol}: {len(unusual)} unusual contracts detected "
            f"({call_count} calls, {put_count} puts)"
        )

    if pc_ratio < 0.3 and call_vol > 1000:
        alerts.append(f"{symbol}: Extremely low P/C ratio ({pc_ratio:.2f}) -- heavy call buying")
    elif pc_ratio > 2.0 and put_vol > 1000:
        alerts.append(f"{symbol}: High P/C ratio ({pc_ratio:.2f}) -- heavy put buying")

    # Check for large premium single contracts
    for c in unusual[:3]:
        if c.last_price and c.volume * c.last_price * 100 > 500_000:
            premium = c.volume * c.last_price * 100
            alerts.append(
                f"{symbol}: ${premium:,.0f} in {c.contract_type} premium "
                f"(${c.strike} {c.expiration.strftime('%m/%d')}, Vol/OI: {c.vol_oi_ratio:.1f}x)"
            )

    return alerts


def screen_universe(symbols: list[str], top_n: int = 20) -> list[OptionsFlowResult]:
    """Screen multiple symbols for unusual options activity.

    Due to Polygon's 5 calls/min rate limit, this scans symbols
    sequentially. For 20 symbols, expect ~4 minutes.
    """
    # Filter to stocks only (no crypto, no ETFs for options)
    stock_symbols = [s for s in symbols if "/" not in s]

    results = []
    for symbol in stock_symbols:
        try:
            result = analyze_symbol(symbol)
            if result and (result.unusual_contracts or result.alert_reasons):
                results.append(result)
        except Exception as e:
            logger.debug("Options flow failed for %s: %s", symbol, e)
            continue

        # Stop if we have enough results (rate limit conservation)
        if len(results) >= top_n:
            break

    results.sort(
        key=lambda r: (len(r.alert_reasons), len(r.unusual_contracts)),
        reverse=True,
    )
    return results[:top_n]


def screen_batch(symbols: list[str], batch_size: int = 5) -> list[OptionsFlowResult]:
    """Scan a small batch of symbols (designed for background loop).

    Scans at most batch_size symbols per call to stay within rate limits.
    Call this every 2 minutes from the refresh loop.
    """
    stock_symbols = [s for s in symbols if "/" not in s][:batch_size]
    results = []

    for symbol in stock_symbols:
        try:
            result = analyze_symbol(symbol)
            if result:
                results.append(result)
        except Exception as e:
            logger.debug("Options flow batch failed for %s: %s", symbol, e)
            continue

    return results
