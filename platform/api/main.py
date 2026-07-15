"""
SEPHIROTH — FastAPI backend.

Local-first: all LLM inference runs through Ollama on the host machine.
Launch (from repo root, with `platform/` on PYTHONPATH):

    PYTHONPATH=.:platform uvicorn api.main:app --reload
"""

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.routers import agents, dashboard, medical, patients, rag
from auth import router as auth_router_module
from core.config import settings
from core.db import init_db
from core.logging import setup_logging

setup_logging(debug=settings.debug)
request_logger = logging.getLogger("api.request")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
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
    allow_origins=["http://localhost:3000", "http://localhost:3100"],
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


app.include_router(auth_router_module.router, prefix="/api/auth", tags=["auth"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(patients.router, prefix="/api/patients", tags=["patients"])
app.include_router(medical.router, prefix="/api/medical", tags=["medical"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.api_version, "model": settings.ollama_model}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
