"""Tax lot optimizer - suggest which lots to sell for tax efficiency.

Feature #27. Uses Alpaca positions data with estimated cost basis.
"""

import logging
from datetime import datetime, timezone

from src.trading.paper import get_positions

logger = logging.getLogger("mse.tax")


def optimize_tax_lots() -> dict:
    """Analyze positions for tax-loss harvesting and lot optimization."""
    positions = get_positions()
    if not positions:
        return {"error": "No positions", "harvest_candidates": [], "gains": [], "summary": {}}

    harvest_candidates = []
    gains = []
    total_unrealized_loss = 0
    total_unrealized_gain = 0

    for p in positions:
        pnl = p.get("unrealized_pnl", 0)
        pnl_pct = p.get("unrealized_pnl_pct", 0)
        value = abs(p.get("market_value", 0))

        entry = {
            "symbol": p["symbol"],
            "qty": p.get("qty", 0),
            "entry_price": p.get("entry_price", 0),
            "current_price": p.get("current_price", 0),
            "unrealized_pnl": round(pnl, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2),
            "market_value": round(value, 2),
        }

        if pnl < 0:
            # Tax loss harvesting candidate
            est_tax_savings = abs(pnl) * 0.25  # ~25% tax rate estimate
            entry["est_tax_savings"] = round(est_tax_savings, 2)
            entry["recommendation"] = "harvest" if pnl_pct < -5 else "watch"
            harvest_candidates.append(entry)
            total_unrealized_loss += pnl
        else:
            # Gain - consider holding period
            entry["recommendation"] = "hold_for_ltcg" if pnl_pct < 20 else "consider_taking_profits"
            gains.append(entry)
            total_unrealized_gain += pnl

    harvest_candidates.sort(key=lambda x: x["unrealized_pnl"])
    gains.sort(key=lambda x: x["unrealized_pnl"], reverse=True)

    net = total_unrealized_gain + total_unrealized_loss
    est_tax_impact = net * 0.25 if net > 0 else 0

    return {
        "harvest_candidates": harvest_candidates,
        "gains": gains,
        "summary": {
            "total_unrealized_loss": round(total_unrealized_loss, 2),
            "total_unrealized_gain": round(total_unrealized_gain, 2),
            "net_unrealized": round(net, 2),
            "est_harvestable_savings": round(abs(total_unrealized_loss) * 0.25, 2),
            "est_tax_on_gains": round(est_tax_impact, 2),
            "positions_in_loss": len(harvest_candidates),
            "positions_in_gain": len(gains),
        },
    }
