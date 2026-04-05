"""Sector Flow Dashboard - aggregate dark pool + options flow by sector.

Detects sector rotation by comparing signal density and direction
across sectors.
"""

import logging
from src.scanner.sectors import SECTORS, get_sector
from src.data.models import DarkPoolResult, OptionsFlowResult, ScanResult

logger = logging.getLogger("mse.sector_flow")


def compute_sector_flow(
    dp_results: list[DarkPoolResult],
    of_results: list[OptionsFlowResult],
    mom_results: list[ScanResult],
) -> list[dict]:
    """Aggregate signals by sector and compute flow direction.

    Returns list of sector summaries sorted by flow strength.
    """
    sector_data: dict[str, dict] = {}

    for name in SECTORS:
        sector_data[name] = {
            "sector": name,
            "symbols": len(SECTORS[name]),
            "dp_accumulating": 0,
            "dp_distributing": 0,
            "dp_avg_short_pct": 0.0,
            "of_bullish": 0,
            "of_bearish": 0,
            "of_unusual_count": 0,
            "momentum_count": 0,
            "avg_momentum_score": 0.0,
            "flow_direction": "neutral",
            "flow_strength": 0.0,
        }

    # Dark pool data
    dp_by_sector: dict[str, list[float]] = {s: [] for s in SECTORS}
    for dp in dp_results:
        sector = get_sector(dp.symbol)
        if sector not in sector_data:
            continue
        if dp.trend == "accumulating":
            sector_data[sector]["dp_accumulating"] += 1
        elif dp.trend == "distributing":
            sector_data[sector]["dp_distributing"] += 1
        dp_by_sector[sector].append(dp.recent_short_pct)

    for sector, pcts in dp_by_sector.items():
        if pcts:
            sector_data[sector]["dp_avg_short_pct"] = round(sum(pcts) / len(pcts), 1)

    # Options flow data
    for of in of_results:
        sector = get_sector(of.symbol)
        if sector not in sector_data:
            continue
        if of.flow_sentiment == "bullish":
            sector_data[sector]["of_bullish"] += 1
        elif of.flow_sentiment == "bearish":
            sector_data[sector]["of_bearish"] += 1
        sector_data[sector]["of_unusual_count"] += len(of.unusual_contracts)

    # Momentum data
    mom_by_sector: dict[str, list[float]] = {s: [] for s in SECTORS}
    for m in mom_results:
        sector = get_sector(m.symbol)
        if sector not in sector_data:
            continue
        sector_data[sector]["momentum_count"] += 1
        mom_by_sector[sector].append(m.score)

    for sector, scores in mom_by_sector.items():
        if scores:
            sector_data[sector]["avg_momentum_score"] = round(sum(scores) / len(scores), 1)

    # Compute flow direction and strength
    for sector, d in sector_data.items():
        bullish_signals = d["dp_accumulating"] + d["of_bullish"] + d["momentum_count"]
        bearish_signals = d["dp_distributing"] + d["of_bearish"]
        total = bullish_signals + bearish_signals

        if total == 0:
            d["flow_direction"] = "neutral"
            d["flow_strength"] = 0.0
            continue

        ratio = bullish_signals / total
        if ratio > 0.65:
            d["flow_direction"] = "inflow"
            d["flow_strength"] = round((ratio - 0.5) * 2, 2)
        elif ratio < 0.35:
            d["flow_direction"] = "outflow"
            d["flow_strength"] = round((0.5 - ratio) * 2, 2)
        else:
            d["flow_direction"] = "neutral"
            d["flow_strength"] = round(abs(ratio - 0.5) * 2, 2)

    results = list(sector_data.values())
    results.sort(key=lambda r: r["flow_strength"], reverse=True)
    return results
