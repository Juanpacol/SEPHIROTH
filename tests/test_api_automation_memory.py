"""`/api/automation-memory` (SPEC-015)."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
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


async def _clinician(client, email="memory-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Memory", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def test_write_then_read(client):
    headers = await _clinician(client)
    write_res = await client.put(
        "/api/automation-memory",
        json={"scope": "user", "scope_id": "U1", "key": "reminder_lead_hours", "value": 12},
        headers=headers,
    )
    assert write_res.status_code == 200

    read_res = await client.get(
        "/api/automation-memory", params={"scope": "user", "scope_id": "U1", "key": "reminder_lead_hours"},
        headers=headers,
    )
    assert read_res.json()["value"] == 12


async def test_write_rejects_invalid_key(client):
    headers = await _clinician(client)
    res = await client.put(
        "/api/automation-memory",
        json={"scope": "patient", "scope_id": "P1", "key": "diagnosis", "value": "flu"},
        headers=headers,
    )
    assert res.status_code == 422


async def test_list_allowed_keys(client):
    headers = await _clinician(client)
    res = await client.get("/api/automation-memory/keys", headers=headers)
    assert res.status_code == 200
    assert "quiet_hours" in res.json()
    assert "reminder_lead_hours" in res.json()
