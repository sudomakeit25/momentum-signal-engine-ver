"""Trade journal - track, analyze, and import trades.

Stores trades in Redis. Supports manual entry and Alpaca auto-import.
Computes performance metrics: win rate, expectancy, R-multiples.
"""

import logging
from datetime import datetime, timedelta

from src.data.redis_store import get_trades, save_trade

logger = logging.getLogger("mse.journal")


def import_from_alpaca(days: int = 30) -> list[dict]:
    """Import closed orders from Alpaca as trades.

    Returns list of newly imported trades.
    """
    from src.data.client import _get_trading_client

    try:
        client = _get_trading_client()
        after = (datetime.now() - timedelta(days=days)).isoformat()
        orders = client.get_orders(
            filter={"status": "closed", "after": after, "limit": 100}
        )
    except Exception as e:
        logger.warning("Alpaca order import failed: %s", e)
        return []

    existing = get_trades()
    existing_ids = {t.get("alpaca_order_id") for t in existing if t.get("alpaca_order_id")}

    imported = []
    for order in orders:
        if order.id in existing_ids:
            continue
        if order.filled_qty is None or float(order.filled_qty) == 0:
            continue

        trade = {
            "symbol": order.symbol,
            "side": order.side.value,
            "shares": float(order.filled_qty),
            "entry_price": float(order.filled_avg_price) if order.filled_avg_price else 0,
            "exit_price": None,
            "stop_loss": None,
            "target": None,
            "status": "open",
            "setup_type": "",
            "notes": f"Imported from Alpaca",
            "entry_date": order.filled_at.isoformat() if order.filled_at else order.created_at.isoformat(),
            "exit_date": None,
            "pnl": None,
            "r_multiple": None,
            "alpaca_order_id": str(order.id),
        }
        if save_trade(trade):
            imported.append(trade)

    logger.info("Imported %d trades from Alpaca", len(imported))
    return imported


def compute_stats(trades: list[dict] | None = None) -> dict:
    """Compute performance statistics from the trade journal."""
    if trades is None:
        trades = get_trades()

    closed = [t for t in trades if t.get("status") == "closed" and t.get("pnl") is not None]

    if not closed:
        return {
            "total_trades": len(trades),
            "closed_trades": 0,
            "open_trades": len([t for t in trades if t.get("status") == "open"]),
            "win_rate": 0,
            "avg_pnl": 0,
            "total_pnl": 0,
            "avg_r_multiple": 0,
            "expectancy": 0,
            "largest_win": 0,
            "largest_loss": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "profit_factor": 0,
            "by_setup": {},
        }

    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]

    total_pnl = sum(t["pnl"] for t in closed)
    win_rate = len(wins) / len(closed) * 100 if closed else 0

    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Expectancy: (win_rate * avg_win) + (loss_rate * avg_loss)
    loss_rate = len(losses) / len(closed) if closed else 0
    expectancy = (win_rate / 100 * avg_win) + (loss_rate * avg_loss)

    # R-multiples
    r_multiples = [t["r_multiple"] for t in closed if t.get("r_multiple") is not None]
    avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0

    # By setup type
    by_setup = {}
    for t in closed:
        setup = t.get("setup_type", "unknown") or "unknown"
        if setup not in by_setup:
            by_setup[setup] = {"trades": 0, "wins": 0, "pnl": 0}
        by_setup[setup]["trades"] += 1
        if t["pnl"] > 0:
            by_setup[setup]["wins"] += 1
        by_setup[setup]["pnl"] += t["pnl"]

    for setup in by_setup:
        s = by_setup[setup]
        s["win_rate"] = round(s["wins"] / s["trades"] * 100, 1) if s["trades"] else 0
        s["pnl"] = round(s["pnl"], 2)

    return {
        "total_trades": len(trades),
        "closed_trades": len(closed),
        "open_trades": len([t for t in trades if t.get("status") == "open"]),
        "win_rate": round(win_rate, 1),
        "avg_pnl": round(total_pnl / len(closed), 2),
        "total_pnl": round(total_pnl, 2),
        "avg_r_multiple": round(avg_r, 2),
        "expectancy": round(expectancy, 2),
        "largest_win": round(max((t["pnl"] for t in wins), default=0), 2),
        "largest_loss": round(min((t["pnl"] for t in losses), default=0), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "by_setup": by_setup,
    }
