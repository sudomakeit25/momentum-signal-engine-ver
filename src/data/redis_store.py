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
_LEADERBOARD_KEY = "mse:leaderboard"
_SEEN_SIGNALS_KEY = "mse:seen_signals"  # daily-rolled set of dispatched keys
_SEEN_SIGNALS_DATE_KEY = "mse:seen_signals_date"
_PUSH_TOKENS_KEY = "mse:push_tokens"  # { expo_token: {added_at, platform} }


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


# --- Per-user Storage ---

def get_user_data(user_id: str, key: str) -> list | dict | None:
    """Get user-scoped data from Redis."""
    redis = _get_redis()
    if not redis:
        return None
    try:
        data = redis.get(f"mse:user:{user_id}:{key}")
        if data:
            return json.loads(data) if isinstance(data, str) else data
        return None
    except Exception as e:
        logger.warning("Failed to load user data %s/%s: %s", user_id, key, e)
        return None


def set_user_data(user_id: str, key: str, data) -> bool:
    """Set user-scoped data in Redis."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        redis.set(f"mse:user:{user_id}:{key}", json.dumps(data))
        return True
    except Exception as e:
        logger.warning("Failed to save user data %s/%s: %s", user_id, key, e)
        return False


# --- Signal Leaderboard ---

def record_signal(signal_data: dict) -> bool:
    """Record a generated signal for leaderboard tracking."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        existing = redis.get(_LEADERBOARD_KEY)
        signals = json.loads(existing) if existing else []
        signals.append(signal_data)
        # Keep last 2000 signals
        if len(signals) > 2000:
            signals = signals[-2000:]
        redis.set(_LEADERBOARD_KEY, json.dumps(signals))
        return True
    except Exception as e:
        logger.warning("Failed to record signal: %s", e)
        return False


def get_leaderboard_signals() -> list[dict]:
    """Get all tracked signals for leaderboard."""
    redis = _get_redis()
    if not redis:
        return []
    try:
        data = redis.get(_LEADERBOARD_KEY)
        if data:
            return json.loads(data) if isinstance(data, str) else data
        return []
    except Exception as e:
        logger.warning("Failed to load leaderboard: %s", e)
        return []


def update_leaderboard_signals(signals: list[dict]) -> bool:
    """Bulk update leaderboard signals (for outcome checks)."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        redis.set(_LEADERBOARD_KEY, json.dumps(signals))
        return True
    except Exception as e:
        logger.warning("Failed to update leaderboard: %s", e)
        return False


# --- Seen-signal tracking (dedup for auto-dispatch) ---

def load_seen_signals() -> tuple[set[str], str]:
    """Return (seen_keys, stored_date). Empty set + '' when Redis is absent."""
    redis = _get_redis()
    if not redis:
        return set(), ""
    try:
        raw = redis.get(_SEEN_SIGNALS_KEY)
        date = redis.get(_SEEN_SIGNALS_DATE_KEY) or ""
        if not raw:
            return set(), str(date)
        keys = json.loads(raw) if isinstance(raw, str) else raw
        return set(keys or []), str(date)
    except Exception as e:
        logger.warning("Failed to load seen signals: %s", e)
        return set(), ""


def save_seen_signals(keys: set[str], date_str: str) -> bool:
    """Persist the current seen-signal set + its day stamp."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        redis.set(_SEEN_SIGNALS_KEY, json.dumps(sorted(keys)))
        redis.set(_SEEN_SIGNALS_DATE_KEY, date_str)
        return True
    except Exception as e:
        logger.warning("Failed to save seen signals: %s", e)
        return False


# --- Intraday-pattern session dedup ---
# Distinct from the daily _SEEN_SIGNALS_KEY because the dedup grain
# differs: intraday keys include pattern_type (V-reversal vs breakdown
# on the same symbol can both fire) and reset every trading day.

_INTRADAY_SEEN_KEY = "mse:intraday_seen"
_INTRADAY_SEEN_DATE_KEY = "mse:intraday_seen_date"
_INTRADAY_LATEST_KEY = "mse:intraday_latest"


def load_intraday_seen() -> tuple[set[str], str]:
    redis = _get_redis()
    if not redis:
        return set(), ""
    try:
        raw = redis.get(_INTRADAY_SEEN_KEY)
        date = redis.get(_INTRADAY_SEEN_DATE_KEY) or ""
        if not raw:
            return set(), str(date)
        keys = json.loads(raw) if isinstance(raw, str) else raw
        return set(keys or []), str(date)
    except Exception as e:
        logger.warning("Failed to load intraday seen: %s", e)
        return set(), ""


def save_intraday_seen(keys: set[str], date_str: str) -> bool:
    redis = _get_redis()
    if not redis:
        return False
    try:
        redis.set(_INTRADAY_SEEN_KEY, json.dumps(sorted(keys)))
        redis.set(_INTRADAY_SEEN_DATE_KEY, date_str)
        return True
    except Exception as e:
        logger.warning("Failed to save intraday seen: %s", e)
        return False


def save_intraday_latest(patterns: list[dict]) -> bool:
    """Cache the most recent batch of detections for the REST endpoint."""
    redis = _get_redis()
    if not redis:
        return False
    try:
        redis.set(_INTRADAY_LATEST_KEY, json.dumps(patterns))
        return True
    except Exception as e:
        logger.warning("Failed to save intraday latest: %s", e)
        return False


def load_intraday_latest() -> list[dict]:
    redis = _get_redis()
    if not redis:
        return []
    try:
        raw = redis.get(_INTRADAY_LATEST_KEY)
        if not raw:
            return []
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data or []
    except Exception as e:
        logger.warning("Failed to load intraday latest: %s", e)
        return []


# --- Expo push tokens (mobile app) ---

def get_push_tokens() -> dict[str, dict]:
    """Return a dict mapping Expo token -> metadata ({added_at, platform})."""
    redis = _get_redis()
    if not redis:
        return {}
    try:
        raw = redis.get(_PUSH_TOKENS_KEY)
        if not raw:
            return {}
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Failed to load push tokens: %s", e)
        return {}


def add_push_token(token: str, platform: str = "unknown") -> bool:
    """Register (or refresh) an Expo push token."""
    if not token or not token.startswith("ExponentPushToken"):
        return False
    redis = _get_redis()
    if not redis:
        return False
    try:
        tokens = get_push_tokens()
        tokens[token] = {
            "added_at": datetime.now().isoformat(),
            "platform": platform,
        }
        redis.set(_PUSH_TOKENS_KEY, json.dumps(tokens))
        return True
    except Exception as e:
        logger.warning("Failed to add push token: %s", e)
        return False


def remove_push_token(token: str) -> bool:
    redis = _get_redis()
    if not redis:
        return False
    try:
        tokens = get_push_tokens()
        if token in tokens:
            del tokens[token]
            redis.set(_PUSH_TOKENS_KEY, json.dumps(tokens))
            return True
        return False
    except Exception as e:
        logger.warning("Failed to remove push token: %s", e)
        return False
