"""Ownership/not-found edge cases for scheduling & results that the happy-
path suites don't exercise — ownership checks are the security-relevant
branches worth locking down explicitly."""

from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from auth.security import create_access_token, hash_password
from core.db import get_session
from data.schemas import Patient, User

pytestmark = pytest.mark.asyncio


def _next_monday() -> date:
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7  # always strictly in the future
    return today + timedelta(days=days_ahead)


NEXT_MONDAY = _next_monday()
NEXT_MONDAY_ISO = f"{NEXT_MONDAY}T09:00:00Z"


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="edge-clin@example.org") -> tuple[dict, str]:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Edge", "password": "password123"}
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


@pytest.fixture
async def patient_row(db_session):
    p = Patient(id="PEDGE1", name="Edge Patient", age=33, sex="F", medical_record_number="PT-PEDGE1")
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.fixture
async def patient_token(db_session, patient_row):
    user = User(
        id="user-pedge1",
        email="pedge1@example.org",
        name="Edge Patient",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id=patient_row.id,
    )
    db_session.add(user)
    await db_session.commit()
    return create_access_token(user.id)


async def test_booking_nonexistent_clinician_404(client, patient_row):
    async with client:
        headers, _ = await _clinician(client)
        res = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": "does-not-exist",
                "patient_id": patient_row.id,
                "start_at": NEXT_MONDAY_ISO,
            },
            headers=headers,
        )
        assert res.status_code == 404


async def test_booking_nonexistent_patient_404(client):
    async with client:
        headers, clinician_id = await _clinician(client)
        res = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": "does-not-exist",
                "start_at": NEXT_MONDAY_ISO,
            },
            headers=headers,
        )
        assert res.status_code == 404


async def test_cancel_appointment_by_non_owner_404(client, patient_row, db_session):
    async with client:
        headers_a, clinician_a = await _clinician(client, "edge-a@example.org")
        await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
            headers=headers_a,
        )
        booked = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_a,
                "patient_id": patient_row.id,
                "start_at": NEXT_MONDAY_ISO,
            },
            headers=headers_a,
        )
        appt_id = booked.json()["id"]

        headers_b, _ = await _clinician(client, "edge-b@example.org")
        res = await client.delete(f"/api/scheduling/appointments/{appt_id}", headers=headers_b)
        assert res.status_code == 404


async def test_patient_can_cancel_own_appointment(client, patient_row, patient_token):
    async with client:
        headers, clinician_id = await _clinician(client)
        await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
            headers=headers,
        )
        booked = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": NEXT_MONDAY_ISO,
            },
            headers=headers,
        )
        appt_id = booked.json()["id"]

        res = await client.delete(
            f"/api/scheduling/appointments/{appt_id}", headers={"Authorization": f"Bearer {patient_token}"}
        )
        assert res.status_code == 204


async def test_update_appointment_by_non_owning_clinician_404(client, patient_row):
    async with client:
        headers_a, clinician_a = await _clinician(client, "edge-c@example.org")
        await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
            headers=headers_a,
        )
        booked = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_a,
                "patient_id": patient_row.id,
                "start_at": NEXT_MONDAY_ISO,
            },
            headers=headers_a,
        )
        appt_id = booked.json()["id"]

        headers_b, _ = await _clinician(client, "edge-d@example.org")
        res = await client.patch(
            f"/api/scheduling/appointments/{appt_id}", json={"status": "completed"}, headers=headers_b
        )
        assert res.status_code == 404


async def test_mark_appointment_completed(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
            headers=headers,
        )
        booked = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": NEXT_MONDAY_ISO,
            },
            headers=headers,
        )
        appt_id = booked.json()["id"]

        res = await client.patch(
            f"/api/scheduling/appointments/{appt_id}",
            json={"status": "completed", "notes": "Reviewed labs."},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "completed"
        assert res.json()["notes"] == "Reviewed labs."


async def test_list_appointments_date_filter(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        await client.post(
            "/api/scheduling/availability",
            json={"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
            headers=headers,
        )
        await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": NEXT_MONDAY_ISO,
            },
            headers=headers,
        )

        in_range = await client.get(
            "/api/scheduling/appointments",
            params={"from": f"{NEXT_MONDAY}T00:00:00Z", "to": f"{NEXT_MONDAY + timedelta(days=1)}T00:00:00Z"},
            headers=headers,
        )
        assert len(in_range.json()) == 1

        out_of_range = await client.get(
            "/api/scheduling/appointments",
            params={
                "from": f"{NEXT_MONDAY + timedelta(days=10)}T00:00:00Z",
                "to": f"{NEXT_MONDAY + timedelta(days=11)}T00:00:00Z",
            },
            headers=headers,
        )
        assert out_of_range.json() == []


async def test_delete_nonexistent_exception_404(client):
    async with client:
        headers, _ = await _clinician(client)
        res = await client.delete("/api/scheduling/exceptions/does-not-exist", headers=headers)
        assert res.status_code == 404


async def test_list_shares_clinician_requires_patient_id(client):
    async with client:
        headers, _ = await _clinician(client, "shares-clin@example.org")
        res = await client.get("/api/results/shares", headers=headers)
        assert res.status_code == 422


async def test_update_share_message(client, patient_row, db_session):
    from datetime import date

    from data.schemas import TimelineEvent

    async with client:
        headers, _ = await _clinician(client, "shares-clin2@example.org")
        event = TimelineEvent(patient_id=patient_row.id, date=date(2026, 1, 1), type="lab", title="Panel")
        db_session.add(event)
        await db_session.commit()

        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": patient_row.id, "timeline_event_id": event.id, "message": "Original"},
            headers=headers,
        )
        share_id = share_res.json()["id"]

        updated = await client.patch(
            f"/api/results/shares/{share_id}", json={"message": "Updated message"}, headers=headers
        )
        assert updated.status_code == 200
        assert updated.json()["message"] == "Updated message"
