"""Password hashing and JWT helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from starlette.concurrency import run_in_threadpool

from core.config import settings

ALGORITHM = "HS256"


def _hash_password_sync(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password_sync(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


async def hash_password(password: str) -> str:
    # bcrypt is CPU-bound (~100-250ms at this cost factor) and synchronous;
    # run it off the event loop so one hash doesn't stall every other
    # in-flight request on a single-worker instance.
    return await run_in_threadpool(_hash_password_sync, password)


async def verify_password(password: str, hashed: str) -> bool:
    return await run_in_threadpool(_verify_password_sync, password, hashed)


async def hash_passwords(passwords: list[str]) -> list[str]:
    """Bulk variant — one threadpool hop for N hashes (e.g. MFA recovery
    codes) instead of N sequential ones."""
    return await run_in_threadpool(lambda: [_hash_password_sync(p) for p in passwords])


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
