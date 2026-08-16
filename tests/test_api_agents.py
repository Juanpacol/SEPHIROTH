"""API tests for /api/agents/* — the consultation endpoints.

`api.routers.agents` resolves its LLM client via `get_llm_client()`, a lazy
singleton defined in `sephiroth.models.factory`, so tests swap it by
setting that module's `_client` global (see `patch_llm_factory` in
conftest.py) rather than `dependency_overrides`.

Passing unmodified against the Phase 3 executor is part of that phase's
parity proof (AC-003-03, docs/specs/SPEC-003-agent-runtime.md).

Phase 4 (SPEC-004) added `verification_report`/`abstention` as additive,
optional response fields — `test_consult_returns_citation_report` below gained
one additive assertion for them; no existing assertion changed. Verifies
AC-004-08 (docs/specs/SPEC-004-verification-safety.md).
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routers import agents as agents_router_module
from auth import router as auth_router_module
from core.db import get_session
from tests.conftest import FakeLLMClient

EVIDENCE_SCRIPT = [
    ("tool", "search_clinical_guidelines", {"query": "A1C goal", "top_k": 5}),
    ("answer", "Target A1C <7% [ADA Standards of Care in Diabetes, 2024]."),
]
COORDINATOR_SCRIPT = [
    (
        "answer",
        "Summary: A1C <7% [ADA Standards of Care in Diabetes, 2024]. "
        "This is decision support, not a diagnosis — professional review required.",
    )
]


@pytest.fixture
def app(db_session, monkeypatch):
    import sephiroth.models.factory as factory_module

    fake_client = FakeLLMClient(
        scripts={
            "clinical evidence specialist": EVIDENCE_SCRIPT,
            "coordinating physician-assistant": COORDINATOR_SCRIPT,
        }
    )
    monkeypatch.setattr(factory_module, "_client", fake_client)

    app = FastAPI()
    app.include_router(auth_router_module.router, prefix="/api/auth")
    app.include_router(agents_router_module.router, prefix="/api/agents")

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


CREDS = {"email": "doc@example.org", "name": "Dr. Test", "password": "password123"}


async def _register(client) -> str:
    res = await client.post("/api/auth/register", json=CREDS)
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_consult_requires_auth(client):
    async with client:
        res = await client.post("/api/agents/consult", json={"query": "What A1C goal?"})
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_consult_returns_citation_report(client):
    async with client:
        token = await _register(client)
        res = await client.post(
            "/api/agents/consult",
            json={"query": "What A1C goal is appropriate?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["answer"]
        assert "citation_report" in body
        assert body["citation_report"]["fabricated"] == []
        assert "verification_report" in body
        assert body["abstention"]["status"] == "answer"


@pytest.mark.asyncio
async def test_consult_persists_to_history(client):
    async with client:
        token = await _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        await client.post(
            "/api/agents/consult", json={"query": "What A1C goal is appropriate?"}, headers=headers
        )
        res = await client.get("/api/agents/history", headers=headers)
        assert res.status_code == 200
        history = res.json()
        assert len(history) == 1
        assert history[0]["answer"]


@pytest.mark.asyncio
async def test_history_requires_auth(client):
    async with client:
        res = await client.get("/api/agents/history")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_ask_single_agent_unknown_agent_404(client):
    async with client:
        token = await _register(client)
        res = await client.post(
            "/api/agents/ask",
            json={"agent": "not-a-real-agent", "query": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404
