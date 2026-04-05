"""Paper trading via Alpaca - execute trades directly from the app."""

import logging
from datetime import datetime

from src.data.client import _get_trading_client

logger = logging.getLogger("mse.trading")


def get_positions() -> list[dict]:
    """Get all open positions."""
    try:
        client = _get_trading_client()
        positions = client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "side": "long" if float(p.qty) > 0 else "short",
                "entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pnl": float(p.unrealized_pl),
                "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
                "change_today": float(p.change_today) * 100,
            }
            for p in positions
        ]
    except Exception as e:
        logger.warning("Failed to get positions: %s", e)
        return []


def get_account_info() -> dict:
    """Get paper trading account info."""
    try:
        client = _get_trading_client()
        account = client.get_account()
        return {
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "day_trade_count": account.daytrade_count,
            "pattern_day_trader": account.pattern_day_trader,
        }
    except Exception as e:
        logger.warning("Failed to get account: %s", e)
        return {}


def place_order(
    symbol: str,
    qty: float,
    side: str,
    order_type: str = "market",
    limit_price: float | None = None,
    stop_price: float | None = None,
    time_in_force: str = "day",
) -> dict:
    """Place a paper trade order."""
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopLimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    try:
        client = _get_trading_client()
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        tif = TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC

        if order_type == "market":
            request = MarketOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=order_side,
                time_in_force=tif,
            )
        elif order_type == "limit" and limit_price:
            request = LimitOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=order_side,
                time_in_force=tif,
                limit_price=limit_price,
            )
        elif order_type == "stop_limit" and limit_price and stop_price:
            request = StopLimitOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=order_side,
                time_in_force=tif,
                limit_price=limit_price,
                stop_price=stop_price,
            )
        else:
            return {"error": f"Invalid order type or missing prices: {order_type}"}

        order = client.submit_order(request)
        logger.info("Order placed: %s %s %s @ %s", side, qty, symbol, order_type)

        return {
            "order_id": str(order.id),
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": str(order.qty),
            "type": order.type.value,
            "status": order.status.value,
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
        }
    except Exception as e:
        logger.warning("Order failed: %s", e)
        return {"error": str(e)}


def close_position(symbol: str) -> dict:
    """Close an open position."""
    try:
        client = _get_trading_client()
        client.close_position(symbol.upper())
        logger.info("Position closed: %s", symbol)
        return {"status": "closed", "symbol": symbol.upper()}
    except Exception as e:
        logger.warning("Close position failed: %s", e)
        return {"error": str(e)}


def get_orders(status: str = "open", limit: int = 20) -> list[dict]:
    """Get recent orders."""
    try:
        client = _get_trading_client()
        orders = client.get_orders(filter={"status": status, "limit": limit})
        return [
            {
                "order_id": str(o.id),
                "symbol": o.symbol,
                "side": o.side.value,
                "qty": str(o.qty),
                "filled_qty": str(o.filled_qty) if o.filled_qty else "0",
                "type": o.type.value,
                "status": o.status.value,
                "limit_price": str(o.limit_price) if o.limit_price else None,
                "stop_price": str(o.stop_price) if o.stop_price else None,
                "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
                "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
                "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            }
            for o in orders
        ]
    except Exception as e:
        logger.warning("Failed to get orders: %s", e)
        return []


def cancel_order(order_id: str) -> dict:
    """Cancel an open order."""
    try:
        client = _get_trading_client()
        client.cancel_order_by_id(order_id)
        return {"status": "cancelled", "order_id": order_id}
    except Exception as e:
        logger.warning("Cancel order failed: %s", e)
        return {"error": str(e)}
