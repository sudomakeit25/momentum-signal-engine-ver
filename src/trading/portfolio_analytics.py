"""Portfolio analytics: heat map, drawdown, Sharpe, beta, concentration,
cash allocation, margin, rebalancing, income tracking.
"""

import logging
import numpy as np

from src.data import client as alpaca_client
from src.trading.paper import get_positions, get_account_info
from src.scanner.sectors import get_sector

logger = logging.getLogger("mse.portfolio")


def get_portfolio_analytics() -> dict:
    """Compute all portfolio analytics in one call."""
    positions = get_positions()
    account = get_account_info()

    if not positions or not account:
        return {"error": "No positions or account data"}

    equity = account.get("equity", 0)
    cash = account.get("cash", 0)

    # --- 21. Portfolio Heat Map ---
    heat_map = _compute_heat_map(positions)

    # --- 22. Max Drawdown ---
    drawdown = _compute_drawdown(positions, equity)

    # --- 24. Beta Exposure ---
    beta = _compute_beta(positions)

    # --- 25. Concentration Risk ---
    concentration = _compute_concentration(positions, equity)

    # --- 26. Cash Allocation ---
    cash_allocation = _compute_cash_allocation(cash, equity)

    # --- 28. Margin Usage ---
    margin = _compute_margin(account)

    # --- 29. Rebalancing ---
    rebalancing = _compute_rebalancing(positions, equity)

    # --- 30. Income ---
    income = _compute_income(positions)

    # --- 23. Sharpe Ratio ---
    sharpe = _compute_sharpe(positions)

    total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
    total_value = sum(p.get("market_value", 0) for p in positions)

    return {
        "account": {
            "equity": equity,
            "cash": cash,
            "invested": round(total_value, 2),
            "total_unrealized_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / equity * 100, 2) if equity else 0,
        },
        "positions_count": len(positions),
        "heat_map": heat_map,
        "drawdown": drawdown,
        "sharpe": sharpe,
        "beta": beta,
        "concentration": concentration,
        "cash_allocation": cash_allocation,
        "margin": margin,
        "rebalancing": rebalancing,
        "income": income,
    }


def _compute_heat_map(positions: list[dict]) -> list[dict]:
    """Group positions by sector with P&L coloring."""
    sectors: dict[str, dict] = {}
    for p in positions:
        sector = get_sector(p["symbol"])
        if sector not in sectors:
            sectors[sector] = {"sector": sector, "value": 0, "pnl": 0, "stocks": []}
        sectors[sector]["value"] += p.get("market_value", 0)
        sectors[sector]["pnl"] += p.get("unrealized_pnl", 0)
        sectors[sector]["stocks"].append({
            "symbol": p["symbol"],
            "value": round(p.get("market_value", 0), 2),
            "pnl": round(p.get("unrealized_pnl", 0), 2),
            "pnl_pct": round(p.get("unrealized_pnl_pct", 0), 2),
        })

    result = []
    for s in sectors.values():
        s["value"] = round(s["value"], 2)
        s["pnl"] = round(s["pnl"], 2)
        result.append(s)

    result.sort(key=lambda s: s["value"], reverse=True)
    return result


def _compute_drawdown(positions: list[dict], equity: float) -> dict:
    """Compute current drawdown from peak."""
    if not equity:
        return {"current_drawdown_pct": 0, "status": "unknown"}

    total_pnl_pct = sum(p.get("unrealized_pnl_pct", 0) for p in positions) / len(positions) if positions else 0

    if total_pnl_pct < -10:
        status = "severe"
    elif total_pnl_pct < -5:
        status = "moderate"
    elif total_pnl_pct < 0:
        status = "mild"
    else:
        status = "none"

    return {
        "current_drawdown_pct": round(min(total_pnl_pct, 0), 2),
        "status": status,
        "recommendation": "Reduce exposure" if total_pnl_pct < -5 else "Normal",
    }


def _compute_sharpe(positions: list[dict]) -> dict:
    """Estimate Sharpe-like ratio from current positions."""
    if not positions:
        return {"ratio": 0, "interpretation": "N/A"}

    returns = [p.get("unrealized_pnl_pct", 0) for p in positions]
    avg_return = np.mean(returns)
    std_return = np.std(returns) if np.std(returns) > 0 else 1
    risk_free = 5.0  # approximate risk-free rate

    sharpe = (avg_return - risk_free) / std_return

    if sharpe > 1:
        interp = "Good risk-adjusted returns"
    elif sharpe > 0:
        interp = "Positive but below benchmark"
    else:
        interp = "Negative risk-adjusted returns"

    return {"ratio": round(sharpe, 2), "interpretation": interp}


def _compute_beta(positions: list[dict]) -> dict:
    """Estimate portfolio beta vs SPY."""
    if not positions:
        return {"portfolio_beta": 1.0, "interpretation": "Unknown"}

    # Simple sector-based beta estimates
    sector_betas = {
        "Technology": 1.2, "Fintech": 1.4, "Cloud/Cyber": 1.3,
        "Consumer": 0.9, "Healthcare": 0.8, "Energy": 1.1,
        "Financials": 1.1, "Industrials": 1.0, "Telecom/Media": 0.8,
        "Semiconductors": 1.3, "Software": 1.2, "Real Estate/Utilities": 0.6,
        "Materials": 1.0, "Other": 1.0,
    }

    total_value = sum(abs(p.get("market_value", 0)) for p in positions)
    if total_value == 0:
        return {"portfolio_beta": 1.0, "interpretation": "Unknown"}

    weighted_beta = 0
    for p in positions:
        sector = get_sector(p["symbol"])
        weight = abs(p.get("market_value", 0)) / total_value
        weighted_beta += weight * sector_betas.get(sector, 1.0)

    if weighted_beta > 1.2:
        interp = "Aggressive (high market sensitivity)"
    elif weighted_beta > 0.8:
        interp = "Moderate (market-neutral)"
    else:
        interp = "Defensive (low market sensitivity)"

    return {"portfolio_beta": round(weighted_beta, 2), "interpretation": interp}


def _compute_concentration(positions: list[dict], equity: float) -> dict:
    """Check for concentration risk."""
    if not positions or not equity:
        return {"alerts": [], "max_position_pct": 0}

    alerts = []
    max_pct = 0

    for p in positions:
        pct = abs(p.get("market_value", 0)) / equity * 100
        if pct > max_pct:
            max_pct = pct

        if pct > 20:
            alerts.append({
                "symbol": p["symbol"],
                "pct": round(pct, 1),
                "level": "high" if pct > 30 else "warning",
                "message": f"{p['symbol']} is {pct:.1f}% of portfolio (>20%)",
            })

    return {
        "max_position_pct": round(max_pct, 1),
        "alerts": alerts,
        "diversified": len(alerts) == 0,
    }


def _compute_cash_allocation(cash: float, equity: float) -> dict:
    """Analyze cash allocation."""
    if not equity:
        return {"cash_pct": 0, "recommendation": "Unknown"}

    cash_pct = cash / equity * 100

    if cash_pct > 50:
        rec = "Consider deploying capital. Over 50% in cash is highly conservative."
    elif cash_pct > 30:
        rec = "Healthy cash reserve. Room to add positions on dips."
    elif cash_pct > 10:
        rec = "Normal allocation. Maintain some dry powder."
    else:
        rec = "Low cash. Consider taking some profits to rebuild reserves."

    return {
        "cash": round(cash, 2),
        "cash_pct": round(cash_pct, 1),
        "invested_pct": round(100 - cash_pct, 1),
        "recommendation": rec,
    }


def _compute_margin(account: dict) -> dict:
    """Analyze margin usage."""
    equity = account.get("equity", 0)
    buying_power = account.get("buying_power", 0)
    portfolio = account.get("portfolio_value", equity)

    if equity <= 0:
        return {"margin_used_pct": 0, "status": "unknown"}

    margin_available = buying_power - equity
    margin_used = max(portfolio - equity, 0)
    margin_pct = margin_used / equity * 100 if equity > 0 else 0

    if margin_pct > 50:
        status = "high"
    elif margin_pct > 20:
        status = "moderate"
    else:
        status = "low"

    return {
        "margin_used": round(margin_used, 2),
        "margin_used_pct": round(margin_pct, 1),
        "margin_available": round(max(margin_available, 0), 2),
        "status": status,
    }


def _compute_rebalancing(positions: list[dict], equity: float) -> dict:
    """Check if portfolio needs rebalancing."""
    if not positions or not equity:
        return {"needs_rebalancing": False, "drift_alerts": []}

    # Equal weight target
    target_pct = 100 / len(positions) if positions else 0
    drift_alerts = []

    for p in positions:
        actual_pct = abs(p.get("market_value", 0)) / equity * 100
        drift = actual_pct - target_pct

        if abs(drift) > 5:
            drift_alerts.append({
                "symbol": p["symbol"],
                "actual_pct": round(actual_pct, 1),
                "target_pct": round(target_pct, 1),
                "drift": round(drift, 1),
                "action": "reduce" if drift > 0 else "increase",
            })

    return {
        "target_weight": round(target_pct, 1),
        "needs_rebalancing": len(drift_alerts) > 0,
        "drift_alerts": sorted(drift_alerts, key=lambda d: abs(d["drift"]), reverse=True),
    }


def _compute_income(positions: list[dict]) -> dict:
    """Estimate dividend income from positions."""
    # Rough dividend yield estimates by sector
    sector_yields = {
        "Technology": 0.5, "Fintech": 0, "Cloud/Cyber": 0,
        "Consumer": 1.5, "Healthcare": 1.2, "Energy": 3.0,
        "Financials": 2.0, "Industrials": 1.5, "Telecom/Media": 3.5,
        "Semiconductors": 0.8, "Software": 0, "Real Estate/Utilities": 3.5,
        "Materials": 1.5, "Other": 1.0,
    }

    total_income = 0
    position_income = []

    for p in positions:
        sector = get_sector(p["symbol"])
        est_yield = sector_yields.get(sector, 1.0)
        value = abs(p.get("market_value", 0))
        annual = value * est_yield / 100

        total_income += annual
        if annual > 0:
            position_income.append({
                "symbol": p["symbol"],
                "value": round(value, 2),
                "est_yield_pct": est_yield,
                "est_annual_income": round(annual, 2),
            })

    return {
        "est_annual_income": round(total_income, 2),
        "est_monthly_income": round(total_income / 12, 2),
        "positions": sorted(position_income, key=lambda p: p["est_annual_income"], reverse=True),
    }
