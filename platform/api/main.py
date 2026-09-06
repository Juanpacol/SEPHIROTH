"""
SEPHIROTH — FastAPI backend.

LLM inference runs through the Google Gemini API (see README's privacy
notice). Launch (from repo root, with `platform/` on PYTHONPATH):

    PYTHONPATH=.:platform uvicorn api.main:app --reload
"""

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.routers import (
    agents,
    alerts,
    approvals,
    audit,
    automation_memory,
    badges,
    dashboard,
    encounters,
    followups,
    internal,
    medical,
    notifications,
    patients,
    portal,
    rag,
    results,
    scheduling,
    tasks,
)
from api.workflows.subscriptions import register_subscriptions
from auth import router as auth_router_module
from auth.deps import require_clinician
from core.config import settings
from core.db import init_db
from core.logging import setup_logging
from core.rate_limit import limiter

setup_logging(debug=settings.debug)
request_logger = logging.getLogger("api.request")
logger = logging.getLogger("api.startup")

# Loud, unmissable at every boot — a local `uvicorn --reload` with
# DATABASE_URL pointed at Supabase (easy to do by accident: `.env` is one
# line to edit and boot doesn't otherwise say which database it landed on)
# means every manual `curl`/test run during that session hits real data
# instead of a local sandbox, including the automatic `alembic upgrade
# head` in `init_db()` below.
_db_host = settings.database_url.split("@")[-1].split("/")[0]
logging.getLogger("api.startup").warning("Connecting to database host: %s", _db_host)


@asynccontextmanager
def _log_ai_configuration() -> None:
    """One line saying what this instance will do with patient content.

    SPEC-022 flipped `llm_provider` to `ollama`, so a deployment that set
    `GEMINI_API_KEY` and never set `LLM_PROVIDER` now gets a different model
    than it did yesterday. That is the intended change, but it must not be
    silent -- an operator who reads one line of the boot log should know which
    provider is serving and whether patient data may leave the machine.
    """
    from sephiroth.models.factory import get_llm_client

    info = get_llm_client().describe()
    logger.info(
        "AI provider: %s (model=%s, endpoint=%s, local=%s, phi_egress_allowed=%s)",
        info.provider,
        info.model,
        info.endpoint or "n/a",
        info.local,
        settings.ai_allow_phi,
    )
    if settings.gemini_api_key and info.provider != "gemini":
        logger.warning(
            "GEMINI_API_KEY is set but LLM_PROVIDER is '%s'. Since SPEC-022 the default "
            "provider is 'ollama'; set LLM_PROVIDER=gemini to restore the previous behaviour.",
            info.provider,
        )
    if not info.local and settings.ai_allow_phi:
        logger.warning(
            "Patient content may be sent to %s (%s): AI_ALLOW_PHI is enabled with a non-local provider.",
            info.provider,
            info.endpoint or "unknown endpoint",
        )


async def lifespan(_: FastAPI):
    await init_db()
    register_subscriptions()
    _log_ai_configuration()
    yield


app = FastAPI(
    title=settings.api_title,
    description=(
        "AI-powered decision support for healthcare professionals. "
        "Research/education use — not a medical device."
    ),
    version=settings.api_version,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Defense-in-depth headers absent by default from FastAPI/Starlette.
    HSTS only outside dev/test: it's a promise ("always use HTTPS for this
    host") that would be actively wrong to make while developing over
    plain http://127.0.0.1."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # This API never serves rendered HTML from user content, except the
    # auto-generated docs (Swagger UI needs its own CDN script/style).
    if request.url.path not in ("/docs", "/redoc"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if settings.environment not in ("development", "test"):
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Tag every request with an id and log a one-line summary."""
    request_id = uuid4().hex[:12]
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000)
    request_logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


# Every route in these five routers carries PHI (patient records,
# consultations, or aggregates derived from them) and is clinician-only.
# `dependencies=` at the router level (rather than per-handler
# `Depends(...)`) means a new route added to any of these files is
# protected the moment it exists, closing the class of bug rather than
# today's instances of it.
_clinician_only = [Depends(require_clinician)]

app.include_router(auth_router_module.router, prefix="/api/auth", tags=["auth"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"], dependencies=_clinician_only)
app.include_router(patients.router, prefix="/api/patients", tags=["patients"], dependencies=_clinician_only)
app.include_router(medical.router, prefix="/api/medical", tags=["medical"], dependencies=_clinician_only)
app.include_router(rag.router, prefix="/api/rag", tags=["rag"], dependencies=_clinician_only)
app.include_router(
    dashboard.router, prefix="/api/dashboard", tags=["dashboard"], dependencies=_clinician_only
)
app.include_router(audit.router, prefix="/api/audit", tags=["audit"], dependencies=_clinician_only)
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"], dependencies=_clinician_only)
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"], dependencies=_clinician_only)
app.include_router(
    encounters.router, prefix="/api/encounters", tags=["encounters"], dependencies=_clinician_only
)
app.include_router(
    approvals.router, prefix="/api/approvals", tags=["approvals"], dependencies=_clinician_only
)
app.include_router(
    followups.router, prefix="/api/followups", tags=["followups"], dependencies=_clinician_only
)
app.include_router(
    automation_memory.router,
    prefix="/api/automation-memory",
    tags=["automation-memory"],
    dependencies=_clinician_only,
)
# Patient portal, scheduling, and results: each mixes roles per-route (no
# blanket guard) — see portal.py/scheduling.py/results.py.
app.include_router(portal.router, prefix="/api/portal", tags=["portal"])
app.include_router(scheduling.router, prefix="/api/scheduling", tags=["scheduling"])
app.include_router(results.router, prefix="/api/results", tags=["results"])
# Notifications: every route is scoped to the caller's own identity
# (`get_current_user`), so it mixes roles per-route like the three above
# rather than carrying a blanket clinician-only guard.
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
# Badges: counters only, no PHI, and a patient legitimately has an unread
# count — so it carries `get_current_user` per route rather than a blanket
# clinician guard, like notifications above.
app.include_router(badges.router, prefix="/api/badges", tags=["badges"])
# The workflow tick: no /api prefix, no JWT-based dependency — see
# internal.py's docstring for why. Guarded by its own shared-secret check.
app.include_router(internal.router, tags=["internal"])


@app.get("/health")
async def health_check():
    """Liveness only — no I/O, never flaps. This is what Render's
    `healthCheckPath` polls; pointing it at a DB-touching endpoint would let
    a transient Supabase pooler blip trigger an unnecessary restart."""
    # `describe()` is a pure attribute read, so naming the *running* model
    # costs this probe nothing. It used to print `settings.gemini_model`
    # unconditionally, which named a model that may not be in use at all.
    from sephiroth.models.factory import get_llm_client

    info = get_llm_client().describe()
    return {
        "status": "healthy",
        "version": settings.api_version,
        "model": info.model,
        "provider": info.provider,
        "local_only": info.local,
    }


@app.get("/health/ready")
async def readiness_check(response: Response):
    """Readiness/deep check: real dependency probes, for humans and the
    post-deploy smoke test — not the Render liveness probe above."""
    from sqlalchemy import text

    from core.db import SessionLocal

    checks: dict[str, str] = {}
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
    # A real probe of whatever is configured. The old check asked whether
    # `GEMINI_API_KEY` was set, which reports the local-first deployment --
    # the default since SPEC-022 -- as unconfigured while it is serving
    # requests correctly. A readiness probe that cries wolf gets ignored.
    from sephiroth.models.factory import get_llm_client

    client = get_llm_client()
    info = client.describe()
    try:
        checks["llm"] = "ok" if await client.health() else "unreachable"
    except Exception as exc:
        checks["llm"] = f"error: {type(exc).__name__}"
    checks["llm_provider"] = info.provider
    checks["llm_model"] = info.model

    # Deliberately not part of `ok`: the database is what this instance cannot
    # serve without. A model that is down degrades features (SPEC-022 B-10/11)
    # and must not take the instance out of rotation.
    ok = checks["database"] == "ok"
    if not ok:
        response.status_code = 503
    return {"status": "ready" if ok else "degraded", "checks": checks}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
