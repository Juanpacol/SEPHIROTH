"""`POST /internal/tick` — the auth gate. No JWT, no user; a shared
secret header instead. See `platform/api/routers/internal.py`."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.config import settings
from core.db import get_session

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def test_disabled_engine_returns_disabled_with_no_auth(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_workflow_engine", False)

    res = await client.post("/internal/tick")

    assert res.status_code == 200
    assert res.json() == {"status": "disabled"}


async def test_enabled_engine_rejects_missing_token(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_workflow_engine", True)
    monkeypatch.setattr(settings, "internal_tick_token", "a-real-secret-value-thats-long-enough")

    res = await client.post("/internal/tick")

    assert res.status_code == 401


async def test_enabled_engine_rejects_wrong_token(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_workflow_engine", True)
    monkeypatch.setattr(settings, "internal_tick_token", "a-real-secret-value-thats-long-enough")

    res = await client.post("/internal/tick", headers={"X-Internal-Token": "wrong"})

    assert res.status_code == 401


async def test_enabled_engine_accepts_correct_token_and_runs_a_tick(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_workflow_engine", True)
    monkeypatch.setattr(settings, "internal_tick_token", "a-real-secret-value-thats-long-enough")

    res = await client.post(
        "/internal/tick", headers={"X-Internal-Token": "a-real-secret-value-thats-long-enough"}
    )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "tick_id" in body
    assert body["claimed"] == 0  # no steps seeded in this test's empty DB
