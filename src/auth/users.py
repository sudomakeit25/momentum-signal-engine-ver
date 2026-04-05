"""User management with Redis storage and JWT auth."""

import json
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config.settings import settings

logger = logging.getLogger("mse.auth")

_USERS_KEY = "mse:users"
_LOGIN_ATTEMPTS_KEY = "mse:login_attempts"
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 900  # 15 minutes


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
    import re
    email = email.lower().strip()
    if not email or not password:
        return {"error": "Email and password required"}
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return {"error": "Invalid email format"}
    if len(password) < 6:
        return {"error": "Password must be at least 6 characters"}
    if name and len(name) > 100:
        return {"error": "Name too long"}

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
    """Authenticate a user. Returns user dict with token or error.

    Rate limited: max 5 attempts per email per 15 minutes.
    """
    email = email.lower().strip()

    # Check rate limit
    locked, remaining = _check_rate_limit(email)
    if locked:
        logger.warning("Login locked out for %s (%d min remaining)", email, remaining)
        return {"error": f"Too many login attempts. Try again in {remaining} minutes."}

    users = _load_users()
    user = users.get(email)

    if not user:
        _record_attempt(email)
        logger.warning("Login attempt for non-existent email: %s", email)
        return {"error": "Invalid email or password"}

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        _record_attempt(email)
        logger.warning("Failed login attempt for: %s", email)
        return {"error": "Invalid email or password"}

    # Clear attempts on successful login
    _clear_attempts(email)
    token = _create_token(user["id"], email)
    return {"user_id": user["id"], "email": email, "name": user.get("name", ""), "token": token}


def _check_rate_limit(email: str) -> tuple[bool, int]:
    """Check if login is rate limited. Returns (locked, minutes_remaining)."""
    redis = _get_redis()
    if not redis:
        return False, 0
    try:
        data = redis.get(f"{_LOGIN_ATTEMPTS_KEY}:{email}")
        if not data:
            return False, 0
        import json
        attempts = json.loads(data) if isinstance(data, str) else data
        now = datetime.now(timezone.utc).timestamp()
        # Filter to attempts within the lockout window
        recent = [t for t in attempts if now - t < _LOCKOUT_SECONDS]
        if len(recent) >= _MAX_ATTEMPTS:
            oldest = min(recent)
            remaining = int((_LOCKOUT_SECONDS - (now - oldest)) / 60) + 1
            return True, remaining
        return False, 0
    except Exception:
        return False, 0


def _record_attempt(email: str) -> None:
    """Record a failed login attempt."""
    redis = _get_redis()
    if not redis:
        return
    try:
        import json
        key = f"{_LOGIN_ATTEMPTS_KEY}:{email}"
        data = redis.get(key)
        attempts = json.loads(data) if data else []
        if isinstance(attempts, str):
            attempts = json.loads(attempts)
        now = datetime.now(timezone.utc).timestamp()
        # Keep only recent attempts
        attempts = [t for t in attempts if now - t < _LOCKOUT_SECONDS]
        attempts.append(now)
        redis.set(key, json.dumps(attempts))
    except Exception as e:
        logger.debug("Failed to record login attempt: %s", e)


def _clear_attempts(email: str) -> None:
    """Clear login attempts after successful login."""
    redis = _get_redis()
    if not redis:
        return
    try:
        redis.delete(f"{_LOGIN_ATTEMPTS_KEY}:{email}")
    except Exception:
        pass


def verify_token(token: str) -> dict | None:
    """Verify a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("Expired token used")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid token attempted")
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
