"""User management with Redis storage and JWT auth."""

import json
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config.settings import settings

logger = logging.getLogger("mse.auth")

_USERS_KEY = "mse:users"


def _get_redis():
    from src.data.redis_store import _get_redis as get_redis
    return get_redis()


def _load_users() -> dict[str, dict]:
    """Load all users from Redis. Returns {email: user_dict}."""
    redis = _get_redis()
    if not redis:
        return {}
    try:
        data = redis.get(_USERS_KEY)
        if data:
            return json.loads(data) if isinstance(data, str) else data
        return {}
    except Exception as e:
        logger.warning("Failed to load users: %s", e)
        return {}


def _save_users(users: dict[str, dict]) -> bool:
    redis = _get_redis()
    if not redis:
        return False
    try:
        redis.set(_USERS_KEY, json.dumps(users))
        return True
    except Exception as e:
        logger.warning("Failed to save users: %s", e)
        return False


def register(email: str, password: str, name: str = "") -> dict:
    """Register a new user. Returns user dict or error."""
    email = email.lower().strip()
    if not email or not password:
        return {"error": "Email and password required"}
    if len(password) < 6:
        return {"error": "Password must be at least 6 characters"}

    users = _load_users()
    if email in users:
        return {"error": "Email already registered"}

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = f"u_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

    user = {
        "id": user_id,
        "email": email,
        "name": name or email.split("@")[0],
        "password_hash": hashed,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    users[email] = user
    if not _save_users(users):
        return {"error": "Failed to save user"}

    token = _create_token(user_id, email)
    return {"user_id": user_id, "email": email, "name": user["name"], "token": token}


def login(email: str, password: str) -> dict:
    """Authenticate a user. Returns user dict with token or error."""
    email = email.lower().strip()
    users = _load_users()
    user = users.get(email)

    if not user:
        return {"error": "Invalid email or password"}

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return {"error": "Invalid email or password"}

    token = _create_token(user["id"], email)
    return {"user_id": user["id"], "email": email, "name": user.get("name", ""), "token": token}


def verify_token(token: str) -> dict | None:
    """Verify a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def _create_token(user_id: str, email: str) -> str:
    """Create a JWT token."""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def get_user_key(user_id: str, key: str) -> str:
    """Generate a Redis key scoped to a user."""
    return f"mse:user:{user_id}:{key}"
