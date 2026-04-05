"""FastAPI auth dependencies."""

from fastapi import Header, HTTPException

from src.auth.users import verify_token


def get_current_user(authorization: str = Header(default="")) -> dict:
    """Extract and verify the current user from the Authorization header.

    Usage: add as a dependency to protected endpoints.
    Returns the JWT payload dict with user_id and email.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.replace("Bearer ", "").strip()
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload


def optional_user(authorization: str = Header(default="")) -> dict | None:
    """Like get_current_user but returns None instead of raising 401.

    Useful for endpoints that work for both authenticated and anonymous users.
    """
    if not authorization:
        return None

    token = authorization.replace("Bearer ", "").strip()
    return verify_token(token)
