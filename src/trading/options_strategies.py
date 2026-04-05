"""Options Strategy Builder - visualize spreads and calculate P&L.

Supports common strategies: covered call, protective put, bull/bear
spreads, straddle, strangle, iron condor, butterfly.
"""

import math
from dataclasses import dataclass


@dataclass
class OptionLeg:
    type: str  # "call" | "put"
    strike: float
    premium: float
    side: str  # "buy" | "sell"
    qty: int = 1


STRATEGIES = {
    "long_call": {
        "name": "Long Call",
        "description": "Bullish bet with limited downside",
        "legs": [{"type": "call", "side": "buy", "strike_offset": 0}],
    },
    "long_put": {
        "name": "Long Put",
        "description": "Bearish bet with limited downside",
        "legs": [{"type": "put", "side": "buy", "strike_offset": 0}],
    },
    "covered_call": {
        "name": "Covered Call",
        "description": "Own shares + sell call for income",
        "legs": [{"type": "call", "side": "sell", "strike_offset": 5}],
        "shares": 100,
    },
    "protective_put": {
        "name": "Protective Put",
        "description": "Own shares + buy put for protection",
        "legs": [{"type": "put", "side": "buy", "strike_offset": -5}],
        "shares": 100,
    },
    "bull_call_spread": {
        "name": "Bull Call Spread",
        "description": "Buy lower call, sell higher call (bullish, limited risk)",
        "legs": [
            {"type": "call", "side": "buy", "strike_offset": 0},
            {"type": "call", "side": "sell", "strike_offset": 10},
        ],
    },
    "bear_put_spread": {
        "name": "Bear Put Spread",
        "description": "Buy higher put, sell lower put (bearish, limited risk)",
        "legs": [
            {"type": "put", "side": "buy", "strike_offset": 0},
            {"type": "put", "side": "sell", "strike_offset": -10},
        ],
    },
    "straddle": {
        "name": "Long Straddle",
        "description": "Buy call + put at same strike (bet on big move either way)",
        "legs": [
            {"type": "call", "side": "buy", "strike_offset": 0},
            {"type": "put", "side": "buy", "strike_offset": 0},
        ],
    },
    "strangle": {
        "name": "Long Strangle",
        "description": "Buy OTM call + OTM put (cheaper straddle)",
        "legs": [
            {"type": "call", "side": "buy", "strike_offset": 5},
            {"type": "put", "side": "buy", "strike_offset": -5},
        ],
    },
    "iron_condor": {
        "name": "Iron Condor",
        "description": "Sell OTM call spread + put spread (bet on low volatility)",
        "legs": [
            {"type": "put", "side": "buy", "strike_offset": -15},
            {"type": "put", "side": "sell", "strike_offset": -5},
            {"type": "call", "side": "sell", "strike_offset": 5},
            {"type": "call", "side": "buy", "strike_offset": 15},
        ],
    },
}


def build_strategy(
    strategy_key: str,
    stock_price: float,
    premiums: dict[str, float] | None = None,
) -> dict:
    """Build an options strategy with P&L calculations.

    Args:
        strategy_key: Key from STRATEGIES dict
        stock_price: Current stock price
        premiums: Optional premium overrides {strike_offset: premium}

    Returns strategy details with P&L at various price points.
    """
    template = STRATEGIES.get(strategy_key)
    if not template:
        return {"error": f"Unknown strategy: {strategy_key}"}

    # Build legs
    legs = []
    total_premium = 0
    for leg_template in template["legs"]:
        strike = round(stock_price + leg_template["strike_offset"], 2)
        # Estimate premium using simple model if not provided
        premium = _estimate_premium(
            stock_price, strike, leg_template["type"],
            premiums.get(str(leg_template["strike_offset"]), 0) if premiums else 0,
        )

        leg = OptionLeg(
            type=leg_template["type"],
            strike=strike,
            premium=premium,
            side=leg_template["side"],
        )
        legs.append(leg)

        if leg.side == "buy":
            total_premium -= premium * 100
        else:
            total_premium += premium * 100

    shares = template.get("shares", 0)

    # Calculate P&L at various price points
    price_range = _get_price_range(stock_price, legs)
    pnl_data = []
    for price in price_range:
        pnl = _calculate_pnl(price, legs, shares, stock_price)
        pnl_data.append({"price": round(price, 2), "pnl": round(pnl, 2)})

    # Key metrics
    max_profit = max(p["pnl"] for p in pnl_data)
    max_loss = min(p["pnl"] for p in pnl_data)
    breakevens = _find_breakevens(pnl_data)

    return {
        "strategy": template["name"],
        "description": template["description"],
        "stock_price": stock_price,
        "legs": [
            {
                "type": l.type,
                "strike": l.strike,
                "premium": l.premium,
                "side": l.side,
            }
            for l in legs
        ],
        "shares": shares,
        "net_premium": round(total_premium, 2),
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "breakevens": breakevens,
        "pnl_data": pnl_data,
    }


def _estimate_premium(stock_price: float, strike: float, opt_type: str, override: float = 0) -> float:
    """Simple premium estimation if not provided."""
    if override > 0:
        return override

    # Very rough Black-Scholes-like estimate
    moneyness = abs(stock_price - strike) / stock_price
    base = stock_price * 0.03  # ~3% base premium
    if opt_type == "call":
        itm_bonus = max(stock_price - strike, 0)
    else:
        itm_bonus = max(strike - stock_price, 0)

    premium = base * math.exp(-moneyness * 3) + itm_bonus
    return round(max(premium, 0.05), 2)


def _get_price_range(stock_price: float, legs: list[OptionLeg]) -> list[float]:
    """Generate price range for P&L chart."""
    all_strikes = [l.strike for l in legs]
    low = min(all_strikes + [stock_price]) * 0.8
    high = max(all_strikes + [stock_price]) * 1.2
    step = (high - low) / 50
    return [low + i * step for i in range(51)]


def _calculate_pnl(price: float, legs: list[OptionLeg], shares: int, entry_price: float) -> float:
    """Calculate P&L at a given stock price at expiration."""
    pnl = 0

    # Stock position P&L
    if shares > 0:
        pnl += (price - entry_price) * shares

    # Options P&L
    for leg in legs:
        if leg.type == "call":
            intrinsic = max(price - leg.strike, 0)
        else:
            intrinsic = max(leg.strike - price, 0)

        if leg.side == "buy":
            pnl += (intrinsic - leg.premium) * 100 * leg.qty
        else:
            pnl += (leg.premium - intrinsic) * 100 * leg.qty

    return pnl


def _find_breakevens(pnl_data: list[dict]) -> list[float]:
    """Find breakeven prices (where P&L crosses zero)."""
    breakevens = []
    for i in range(1, len(pnl_data)):
        prev = pnl_data[i - 1]["pnl"]
        curr = pnl_data[i]["pnl"]
        if (prev < 0 and curr >= 0) or (prev >= 0 and curr < 0):
            # Linear interpolation
            p1 = pnl_data[i - 1]["price"]
            p2 = pnl_data[i]["price"]
            ratio = abs(prev) / (abs(prev) + abs(curr))
            breakeven = p1 + (p2 - p1) * ratio
            breakevens.append(round(breakeven, 2))
    return breakevens


def list_strategies() -> list[dict]:
    """List all available strategies."""
    return [
        {"key": k, "name": v["name"], "description": v["description"], "legs": len(v["legs"])}
        for k, v in STRATEGIES.items()
    ]
