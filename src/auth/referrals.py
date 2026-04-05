"""Referral program - invite friends, track referrals.

Feature #83. Stored in Redis.
"""

import json
import hashlib
import logging
from datetime import datetime, timezone

from src.data.redis_store import _get_redis

logger = logging.getLogger("mse.referrals")

_REFERRALS_KEY = "mse:referrals"


def generate_referral_code(user_id: str) -> str:
    """Generate a unique referral code for a user."""
    return hashlib.md5(f"ref_{user_id}".encode()).hexdigest()[:8]


def get_referral_stats(user_id: str) -> dict:
    """Get referral stats for a user."""
    redis = _get_redis()
    if not redis:
        return {"code": generate_referral_code(user_id), "referrals": 0, "history": []}

    try:
        data = redis.get(_REFERRALS_KEY)
        all_referrals = json.loads(data) if data else {}
        user_refs = all_referrals.get(user_id, [])

        return {
            "code": generate_referral_code(user_id),
            "referrals": len(user_refs),
            "history": user_refs[-20:],
            "link": f"https://momentum-signal-engine.vercel.app/login?ref={generate_referral_code(user_id)}",
        }
    except Exception:
        return {"code": generate_referral_code(user_id), "referrals": 0, "history": []}


def record_referral(referral_code: str, new_user_email: str) -> bool:
    """Record a referral when a new user signs up with a code."""
    redis = _get_redis()
    if not redis:
        return False

    try:
        # Find the referrer
        from src.auth.users import _load_users
        users = _load_users()
        referrer_id = None
        for email, user in users.items():
            if generate_referral_code(user["id"]) == referral_code:
                referrer_id = user["id"]
                break

        if not referrer_id:
            return False

        data = redis.get(_REFERRALS_KEY)
        all_referrals = json.loads(data) if data else {}
        if referrer_id not in all_referrals:
            all_referrals[referrer_id] = []

        all_referrals[referrer_id].append({
            "email": new_user_email,
            "date": datetime.now(timezone.utc).isoformat(),
        })

        redis.set(_REFERRALS_KEY, json.dumps(all_referrals))
        logger.info("Referral recorded: %s referred %s", referrer_id, new_user_email)
        return True
    except Exception as e:
        logger.warning("Referral recording failed: %s", e)
        return False
