"""Password hashing and JWT helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    return jwt.encode({"sub": user_id, "exp": expires}, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """Return the user id, or None when the token is invalid/expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("purpose") is not None:
            return None  # reject an MFA-pending token presented as a full access token
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


MFA_PENDING_TTL_MINUTES = 5


def create_mfa_pending_token(user_id: str) -> str:
    """A short-lived, single-purpose token issued after a correct
    password when the account has TOTP enabled. It authorizes only
    `POST /api/auth/login/mfa` — `decode_access_token` explicitly rejects
    any token carrying `purpose`, so this can never be replayed as a full
    session token even before it expires."""
    expires = datetime.now(timezone.utc) + timedelta(minutes=MFA_PENDING_TTL_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expires, "purpose": "mfa_pending"}, settings.jwt_secret, algorithm=ALGORITHM
    )


def decode_mfa_pending_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("purpose") != "mfa_pending":
            return None
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
