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
    res = await client.post(
        "/api/auth/register",
        json={"email": "memory-write@example.org", "name": "Dr. Write", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    clinician_id = res.json()["user"]["id"]

    write_res = await client.put(
        "/api/automation-memory",
        json={"scope": "user", "scope_id": clinician_id, "key": "reminder_lead_hours", "value": 12},
        headers=headers,
    )
    assert write_res.status_code == 200

    read_res = await client.get(
        "/api/automation-memory",
        params={"scope": "user", "scope_id": clinician_id, "key": "reminder_lead_hours"},
        headers=headers,
    )
    assert read_res.json()["value"] == 12


async def test_write_rejects_nonexistent_user(client):
    headers = await _clinician(client)
    res = await client.put(
        "/api/automation-memory",
        json={"scope": "user", "scope_id": "no-such-user", "key": "reminder_lead_hours", "value": 12},
        headers=headers,
    )
    assert res.status_code == 422


async def test_write_rejects_malformed_value(client):
    headers = await _clinician(client)
    res = await client.put(
        "/api/automation-memory",
        json={"scope": "clinic", "scope_id": "default", "key": "reminder_lead_hours", "value": "not-an-int"},
        headers=headers,
    )
    assert res.status_code == 422


async def test_write_rejects_out_of_range_value(client):
    headers = await _clinician(client)
    res = await client.put(
        "/api/automation-memory",
        json={"scope": "clinic", "scope_id": "default", "key": "reminder_lead_hours", "value": 9999},
        headers=headers,
    )
    assert res.status_code == 422


async def test_write_rejects_malformed_quiet_hours(client):
    headers = await _clinician(client)
    res = await client.put(
        "/api/automation-memory",
        json={"scope": "clinic", "scope_id": "default", "key": "quiet_hours", "value": {"start": "25:99"}},
        headers=headers,
    )
    assert res.status_code == 422


async def test_write_accepts_clinic_scope_with_any_id(client):
    """`clinic` has no backing table (single-tenant app) -- any scope_id
    is accepted, unlike `user`/`patient`."""
    headers = await _clinician(client)
    res = await client.put(
        "/api/automation-memory",
        json={"scope": "clinic", "scope_id": "whatever-id", "key": "reminder_lead_hours", "value": 12},
        headers=headers,
    )
    assert res.status_code == 200


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
