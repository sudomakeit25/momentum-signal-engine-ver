"""Redis storage helpers for persistent data (trades, alerts, watchlist).

Uses Upstash Redis for data that must survive Render restarts.
Falls back gracefully if Redis is not configured.
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger("mse.redis_store")

_TRADES_KEY = "mse:trades"
_ALERT_HISTORY_KEY = "mse:alert_history"
_WATCHLIST_KEY = "mse:watchlist"


def _get_redis():
    """Get Upstash Redis client, or None if not configured."""
    from config.settings import settings
    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        try:
            from upstash_redis import Redis
            return Redis(
                url=settings.upstash_redis_rest_url,
                token=settings.upstash_redis_rest_token,
            )
        except Exception as e:
            logger.warning("Redis connection failed: %s", e)
    return None


# --- Trade Journal ---

def save_trade(trade: dict) -> bool:
    """Append a trade to the journal."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        trade["id"] = f"t_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        trade["created_at"] = datetime.now().isoformat()
        existing = redis.get(_TRADES_KEY)
        trades = json.loads(existing) if existing else []
        trades.append(trade)
        redis.set(_TRADES_KEY, json.dumps(trades))
        return True
    except Exception as e:
        logger.warning("Failed to save trade: %s", e)
        return False


def get_trades() -> list[dict]:
    """Get all trades from the journal."""
    redis = _get_redis()
    if not redis:
        return []
    try:
        data = redis.get(_TRADES_KEY)
        if data:
            if isinstance(data, str):
                return json.loads(data)
            return data
        return []
    except Exception as e:
        logger.warning("Failed to load trades: %s", e)
        return []


def delete_trade(trade_id: str) -> bool:
    """Delete a trade by ID."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        trades = get_trades()
        trades = [t for t in trades if t.get("id") != trade_id]
        redis.set(_TRADES_KEY, json.dumps(trades))
        return True
    except Exception as e:
        logger.warning("Failed to delete trade: %s", e)
        return False


def update_trade(trade_id: str, updates: dict) -> bool:
    """Update a trade by ID."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        trades = get_trades()
        for t in trades:
            if t.get("id") == trade_id:
                t.update(updates)
                break
        redis.set(_TRADES_KEY, json.dumps(trades))
        return True
    except Exception as e:
        logger.warning("Failed to update trade: %s", e)
        return False


# --- Alert History ---

def log_alert(alert: dict) -> bool:
    """Log a dispatched alert."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        alert["timestamp"] = datetime.now().isoformat()
        existing = redis.get(_ALERT_HISTORY_KEY)
        history = json.loads(existing) if existing else []
        history.append(alert)
        # Keep last 500 alerts
        if len(history) > 500:
            history = history[-500:]
        redis.set(_ALERT_HISTORY_KEY, json.dumps(history))
        return True
    except Exception as e:
        logger.warning("Failed to log alert: %s", e)
        return False


def get_alert_history(limit: int = 100) -> list[dict]:
    """Get alert history, most recent first."""
    redis = _get_redis()
    if not redis:
        return []
    try:
        data = redis.get(_ALERT_HISTORY_KEY)
        if data:
            history = json.loads(data) if isinstance(data, str) else data
            history.reverse()
            return history[:limit]
        return []
    except Exception as e:
        logger.warning("Failed to load alert history: %s", e)
        return []


# --- Server-side Watchlist ---

def get_watchlist() -> list[str]:
    """Get the watchlist from Redis."""
    redis = _get_redis()
    if not redis:
        return []
    try:
        data = redis.get(_WATCHLIST_KEY)
        if data:
            return json.loads(data) if isinstance(data, str) else data
        return []
    except Exception as e:
        logger.warning("Failed to load watchlist: %s", e)
        return []


def save_watchlist(symbols: list[str]) -> bool:
    """Save the watchlist to Redis."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        redis.set(_WATCHLIST_KEY, json.dumps(symbols))
        return True
    except Exception as e:
        logger.warning("Failed to save watchlist: %s", e)
        return False
