"""Shared slowapi `Limiter`, imported by `api.main` (global wiring) and any
router applying a per-route limit (`auth.router`, `api.intelligence.routers.agents`) — one
instance so every limit shares the same in-memory bucket store."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from core.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
# The test suite hammers /login, /register, /consult etc. from the same
# in-process client far faster than any real user could — rate limiting
# would make test order/count affect pass/fail instead of the behavior
# under test. Same "off in test" posture as HSTS in api/main.py.
limiter.enabled = settings.environment != "test"


def key_by_user_or_ip(request: Request) -> str:
    """Key on the authenticated user (from the bearer token) so one clinic's
    shared IP doesn't throttle every clinician together, falling back to
    remote address for an unauthenticated/malformed request — matches
    `auth.deps.get_current_user`'s own token decoding, just done here purely
    to pick a rate-limit bucket, before that dependency ever runs."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        from auth.security import decode_access_token

        user_id = decode_access_token(auth_header[7:])
        if user_id:
            return f"user:{user_id}"
    return get_remote_address(request)
