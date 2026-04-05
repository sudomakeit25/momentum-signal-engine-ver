"""Community Feed and Signal Sharing.

Stores shared signals and community posts in Redis.
"""

import json
import logging
import hashlib
from datetime import datetime, timezone

from src.data.redis_store import _get_redis

logger = logging.getLogger("mse.community")

_SHARED_SIGNALS_KEY = "mse:shared_signals"
_COMMUNITY_FEED_KEY = "mse:community_feed"


# --- Share Signals ---

def share_signal(signal_data: dict, user_id: str = "", user_name: str = "") -> dict:
    """Create a shareable signal. Returns the share ID."""
    share_id = hashlib.md5(
        f"{signal_data.get('symbol', '')}{datetime.now().isoformat()}{user_id}".encode()
    ).hexdigest()[:12]

    shared = {
        "id": share_id,
        "signal": signal_data,
        "user_id": user_id,
        "user_name": user_name or "Anonymous",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "views": 0,
    }

    redis = _get_redis()
    if not redis:
        return {"error": "Redis not available"}

    try:
        # Store individual shared signal
        redis.set(f"mse:share:{share_id}", json.dumps(shared))

        # Add to shared signals list
        existing = redis.get(_SHARED_SIGNALS_KEY)
        signals = json.loads(existing) if existing else []
        signals.append({"id": share_id, "symbol": signal_data.get("symbol", ""), "created_at": shared["created_at"]})
        if len(signals) > 500:
            signals = signals[-500:]
        redis.set(_SHARED_SIGNALS_KEY, json.dumps(signals))

        return {"share_id": share_id, "url": f"/shared/{share_id}"}
    except Exception as e:
        logger.warning("Failed to share signal: %s", e)
        return {"error": str(e)}


def get_shared_signal(share_id: str) -> dict | None:
    """Get a shared signal by ID."""
    redis = _get_redis()
    if not redis:
        return None

    try:
        data = redis.get(f"mse:share:{share_id}")
        if not data:
            return None
        shared = json.loads(data) if isinstance(data, str) else data

        # Increment view count
        shared["views"] = shared.get("views", 0) + 1
        redis.set(f"mse:share:{share_id}", json.dumps(shared))

        return shared
    except Exception as e:
        logger.warning("Failed to get shared signal: %s", e)
        return None


def get_recent_shares(limit: int = 20) -> list[dict]:
    """Get recently shared signals."""
    redis = _get_redis()
    if not redis:
        return []

    try:
        data = redis.get(_SHARED_SIGNALS_KEY)
        if not data:
            return []
        signals = json.loads(data) if isinstance(data, str) else data
        return list(reversed(signals[-limit:]))
    except Exception:
        return []


# --- Community Feed ---

def create_post(
    user_id: str,
    user_name: str,
    content: str,
    symbol: str = "",
    trade_data: dict | None = None,
) -> dict:
    """Create a community feed post."""
    if len(content) > 500:
        return {"error": "Post too long (max 500 characters)"}

    post_id = hashlib.md5(
        f"{user_id}{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]

    post = {
        "id": post_id,
        "user_id": user_id,
        "user_name": user_name,
        "content": content,
        "symbol": symbol.upper() if symbol else "",
        "trade_data": trade_data,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "likes": 0,
        "comments": [],
    }

    redis = _get_redis()
    if not redis:
        return {"error": "Redis not available"}

    try:
        existing = redis.get(_COMMUNITY_FEED_KEY)
        feed = json.loads(existing) if existing else []
        feed.append(post)
        if len(feed) > 1000:
            feed = feed[-1000:]
        redis.set(_COMMUNITY_FEED_KEY, json.dumps(feed))
        return {"post_id": post_id}
    except Exception as e:
        logger.warning("Failed to create post: %s", e)
        return {"error": str(e)}


def get_feed(limit: int = 50, symbol: str = "") -> list[dict]:
    """Get community feed posts."""
    redis = _get_redis()
    if not redis:
        return []

    try:
        data = redis.get(_COMMUNITY_FEED_KEY)
        if not data:
            return []
        feed = json.loads(data) if isinstance(data, str) else data

        if symbol:
            feed = [p for p in feed if p.get("symbol") == symbol.upper()]

        return list(reversed(feed[-limit:]))
    except Exception:
        return []


def add_comment(post_id: str, user_id: str, user_name: str, content: str) -> dict:
    """Add a comment to a post."""
    if len(content) > 300:
        return {"error": "Comment too long (max 300 characters)"}

    redis = _get_redis()
    if not redis:
        return {"error": "Redis not available"}

    try:
        existing = redis.get(_COMMUNITY_FEED_KEY)
        feed = json.loads(existing) if existing else []

        for post in feed:
            if post["id"] == post_id:
                comment = {
                    "user_id": user_id,
                    "user_name": user_name,
                    "content": content,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                post.setdefault("comments", []).append(comment)
                break

        redis.set(_COMMUNITY_FEED_KEY, json.dumps(feed))
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


def like_post(post_id: str) -> dict:
    """Like a post."""
    redis = _get_redis()
    if not redis:
        return {"error": "Redis not available"}

    try:
        existing = redis.get(_COMMUNITY_FEED_KEY)
        feed = json.loads(existing) if existing else []

        for post in feed:
            if post["id"] == post_id:
                post["likes"] = post.get("likes", 0) + 1
                redis.set(_COMMUNITY_FEED_KEY, json.dumps(feed))
                return {"likes": post["likes"]}

        return {"error": "Post not found"}
    except Exception as e:
        return {"error": str(e)}
