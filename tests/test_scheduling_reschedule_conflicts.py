"""`PATCH /api/scheduling/appointments/{id}` (reschedule) previously had no
overlap re-check at all — this closes that gap. Uses the same fixtures/
patterns as `test_api_scheduling_appointments.py`."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import Patient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="resched-clin@example.org") -> tuple[dict, str]:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Resched", "password": "password123"}
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


@pytest.fixture
async def patient_row(db_session):
    p = Patient(id="PRESCHED1", name="Resched Patient", age=30, sex="M", medical_record_number="PT-PRESCHED1")
    db_session.add(p)
    await db_session.commit()
    return p


async def _set_up_availability(client, headers):
    await client.post(
        "/api/scheduling/availability",
        json={"weekday": 0, "start_time": "09:00", "end_time": "12:00", "slot_minutes": 30},
        headers=headers,
    )


NEXT_MONDAY_ISO = "2026-08-24T09:00:00Z"  # 2026-08-24 is a Monday


async def test_reschedule_into_occupied_slot_is_rejected(client, patient_row, db_session):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        occupied = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        assert occupied.status_code == 201

        p2 = Patient(id="PRESCHED2", name="Second", age=40, sex="F", medical_record_number="PT-PRESCHED2")
        db_session.add(p2)
        await db_session.commit()
        movable = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": p2.id,
                "start_at": "2026-08-24T10:00:00Z",
            },
            headers=headers,
        )
        assert movable.status_code == 201
        movable_id = movable.json()["id"]

        res = await client.patch(
            f"/api/scheduling/appointments/{movable_id}",
            json={"start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        assert res.status_code == 409


async def test_reschedule_within_own_current_slot_succeeds(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        booked = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        appt_id = booked.json()["id"]

        # "Reschedule" to the exact same start time it already occupies —
        # must not collide with itself.
        res = await client.patch(
            f"/api/scheduling/appointments/{appt_id}",
            json={"start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        assert res.status_code == 200


async def test_reschedule_to_a_free_slot_succeeds(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        booked = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        appt_id = booked.json()["id"]

        res = await client.patch(
            f"/api/scheduling/appointments/{appt_id}",
            json={"start_at": "2026-08-24T11:00:00Z"},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["start_at"] == "2026-08-24T11:00:00"


async def test_reschedule_of_cancelled_appointment_skips_conflict_check(client, patient_row, db_session):
    """A cancelled appointment being edited (e.g. correcting its notes/
    status after the fact) shouldn't be blocked by conflict rules that
    only make sense for a live booking."""
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        occupied = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        assert occupied.status_code == 201

        p2 = Patient(id="PRESCHED3", name="Third", age=45, sex="M", medical_record_number="PT-PRESCHED3")
        db_session.add(p2)
        await db_session.commit()
        movable = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": p2.id,
                "start_at": "2026-08-24T10:00:00Z",
            },
            headers=headers,
        )
        movable_id = movable.json()["id"]
        await client.delete(f"/api/scheduling/appointments/{movable_id}", headers=headers)

        res = await client.patch(
            f"/api/scheduling/appointments/{movable_id}",
            json={"start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        assert res.status_code == 200
