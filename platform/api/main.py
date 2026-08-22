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

from api.routers import (
    agents,
    alerts,
    approvals,
    audit,
    automation_memory,
    dashboard,
    followups,
    internal,
    medical,
    notifications,
    patients,
    portal,
    rag,
    results,
    scheduling,
)
from api.workflows.subscriptions import register_subscriptions
from auth import router as auth_router_module
from auth.deps import require_clinician
from core.config import settings
from core.db import init_db
from core.logging import setup_logging

setup_logging(debug=settings.debug)
request_logger = logging.getLogger("api.request")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    register_subscriptions()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
# The workflow tick: no /api prefix, no JWT-based dependency — see
# internal.py's docstring for why. Guarded by its own shared-secret check.
app.include_router(internal.router, tags=["internal"])


@app.get("/health")
async def health_check():
    """Liveness only — no I/O, never flaps. This is what Render's
    `healthCheckPath` polls; pointing it at a DB-touching endpoint would let
    a transient Supabase pooler blip trigger an unnecessary restart."""
    return {"status": "healthy", "version": settings.api_version, "model": settings.gemini_model}


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
    checks["llm"] = "configured" if settings.gemini_api_key else "unconfigured"

    ok = checks["database"] == "ok"
    if not ok:
        response.status_code = 503
    return {"status": "ready" if ok else "degraded", "checks": checks}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
