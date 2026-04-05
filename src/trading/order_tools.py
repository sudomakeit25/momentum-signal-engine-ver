"""Order tools: DCA scheduler, trailing stop, bracket orders.

Features 57-59.
"""

import logging
import json
from datetime import datetime, timezone

from src.data.redis_store import _get_redis
from src.trading.paper import place_order

logger = logging.getLogger("mse.order_tools")

_DCA_KEY = "mse:dca_schedules"
_TRAILING_KEY = "mse:trailing_stops"


# --- 57. DCA Scheduler ---

def get_dca_schedules() -> list[dict]:
    redis = _get_redis()
    if not redis:
        return []
    try:
        data = redis.get(_DCA_KEY)
        return json.loads(data) if data else []
    except Exception:
        return []


def add_dca_schedule(symbol: str, amount: float, frequency: str = "weekly") -> dict:
    """Add a dollar-cost averaging schedule."""
    schedules = get_dca_schedules()
    schedule = {
        "id": f"dca_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "symbol": symbol.upper(),
        "amount": amount,
        "frequency": frequency,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_executed": None,
        "total_invested": 0,
        "executions": 0,
    }
    schedules.append(schedule)
    redis = _get_redis()
    if redis:
        redis.set(_DCA_KEY, json.dumps(schedules))
    return schedule


def remove_dca_schedule(schedule_id: str) -> bool:
    schedules = get_dca_schedules()
    schedules = [s for s in schedules if s.get("id") != schedule_id]
    redis = _get_redis()
    if redis:
        redis.set(_DCA_KEY, json.dumps(schedules))
        return True
    return False


def execute_dca(schedule: dict) -> dict:
    """Execute a DCA buy for a schedule."""
    from src.data import client as alpaca_client

    try:
        df = alpaca_client.get_bars(schedule["symbol"], days=5)
        if df is None or df.empty:
            return {"error": "No price data"}

        price = float(df["close"].iloc[-1])
        qty = round(schedule["amount"] / price, 4)

        if qty <= 0:
            return {"error": "Amount too small for current price"}

        result = place_order(schedule["symbol"], qty, "buy", "market")
        return result
    except Exception as e:
        return {"error": str(e)}


# --- 58. Trailing Stop Manager ---

def get_trailing_stops() -> list[dict]:
    redis = _get_redis()
    if not redis:
        return []
    try:
        data = redis.get(_TRAILING_KEY)
        return json.loads(data) if data else []
    except Exception:
        return []


def add_trailing_stop(symbol: str, trail_pct: float, entry_price: float) -> dict:
    """Add a trailing stop."""
    stops = get_trailing_stops()
    stop = {
        "id": f"ts_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "symbol": symbol.upper(),
        "trail_pct": trail_pct,
        "entry_price": entry_price,
        "highest_price": entry_price,
        "stop_price": round(entry_price * (1 - trail_pct / 100), 2),
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "triggered": False,
    }
    stops.append(stop)
    redis = _get_redis()
    if redis:
        redis.set(_TRAILING_KEY, json.dumps(stops))
    return stop


def check_trailing_stops() -> list[dict]:
    """Check all trailing stops against current prices."""
    from src.data import client as alpaca_client

    stops = get_trailing_stops()
    triggered = []
    updated = False

    for stop in stops:
        if not stop.get("active") or stop.get("triggered"):
            continue

        try:
            df = alpaca_client.get_bars(stop["symbol"], days=5)
            if df is None or df.empty:
                continue

            current = float(df["close"].iloc[-1])

            # Update highest price
            if current > stop["highest_price"]:
                stop["highest_price"] = current
                stop["stop_price"] = round(current * (1 - stop["trail_pct"] / 100), 2)
                updated = True

            # Check if stop hit
            if current <= stop["stop_price"]:
                stop["triggered"] = True
                stop["active"] = False
                stop["triggered_at"] = datetime.now(timezone.utc).isoformat()
                stop["triggered_price"] = current
                triggered.append(stop)
                updated = True
        except Exception:
            continue

    if updated:
        redis = _get_redis()
        if redis:
            redis.set(_TRAILING_KEY, json.dumps(stops))

    return triggered


# --- 59. Bracket Order Builder ---

def build_bracket_order(symbol: str, qty: float, entry: float, stop_loss: float, take_profit: float) -> dict:
    """Build and submit a bracket order (entry + stop + target)."""
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
    from src.data.client import _get_trading_client

    try:
        client = _get_trading_client()
        order = client.submit_order(
            MarketOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit={"limit_price": take_profit},
                stop_loss={"stop_price": stop_loss},
            )
        )
        return {
            "order_id": str(order.id),
            "symbol": order.symbol,
            "status": order.status.value,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }
    except Exception as e:
        return {"error": str(e)}
