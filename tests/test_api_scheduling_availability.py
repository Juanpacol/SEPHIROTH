"""API tests for `/api/scheduling/availability` and `/exceptions` — a
clinician's own working-hours CRUD, built against the real `api.main.app`
wiring."""

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


async def _clinician_headers(client, email="sched-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Sched", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def test_create_and_list_availability_rule(client):
    async with client:
        headers = await _clinician_headers(client)
        res = await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
            headers=headers,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["timezone"] == "UTC"
        assert body["slot_minutes"] == 30

        listing = await client.get("/api/scheduling/availability", headers=headers)
        assert len(listing.json()["rules"]) == 1


async def test_start_time_after_end_time_rejected(client):
    async with client:
        headers = await _clinician_headers(client)
        res = await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "17:00", "end_time": "09:00"},
            headers=headers,
        )
        assert res.status_code == 422


async def test_overlapping_rule_same_weekday_rejected(client):
    async with client:
        headers = await _clinician_headers(client)
        await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "12:00"},
            headers=headers,
        )
        res = await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "11:00", "end_time": "13:00"},
            headers=headers,
        )
        assert res.status_code == 422


async def test_invalid_timezone_rejected(client):
    async with client:
        headers = await _clinician_headers(client)
        res = await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "10:00", "timezone": "Not/AZone"},
            headers=headers,
        )
        assert res.status_code == 422


async def test_update_and_deactivate_rule(client):
    async with client:
        headers = await _clinician_headers(client)
        created = await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
            headers=headers,
        )
        rule_id = created.json()["id"]

        updated = await client.patch(
            f"/api/scheduling/availability/{rule_id}", json={"active": False}, headers=headers
        )
        assert updated.status_code == 200
        assert updated.json()["active"] is False


async def test_delete_rule(client):
    async with client:
        headers = await _clinician_headers(client)
        created = await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
            headers=headers,
        )
        rule_id = created.json()["id"]
        res = await client.delete(f"/api/scheduling/availability/{rule_id}", headers=headers)
        assert res.status_code == 204
        listing = await client.get("/api/scheduling/availability", headers=headers)
        assert listing.json()["rules"] == []


async def test_another_clinicians_rule_is_404_not_403(client):
    async with client:
        headers_a = await _clinician_headers(client, "sched-a@example.org")
        created = await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
            headers=headers_a,
        )
        rule_id = created.json()["id"]

        headers_b = await _clinician_headers(client, "sched-b@example.org")
        res = await client.patch(
            f"/api/scheduling/availability/{rule_id}", json={"active": False}, headers=headers_b
        )
        assert res.status_code == 404


async def test_create_and_delete_exception(client):
    async with client:
        headers = await _clinician_headers(client)
        res = await client.post(
            "/api/scheduling/exceptions",
            json={"start_at": "2026-02-01T09:00:00", "end_at": "2026-02-01T10:00:00", "kind": "block"},
            headers=headers,
        )
        assert res.status_code == 201
        exc_id = res.json()["id"]

        deleted = await client.delete(f"/api/scheduling/exceptions/{exc_id}", headers=headers)
        assert deleted.status_code == 204


async def test_availability_requires_clinician(client):
    async with client:
        res = await client.get("/api/scheduling/availability")
        assert res.status_code == 401
