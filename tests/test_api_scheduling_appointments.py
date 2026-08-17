"""API tests for `/api/scheduling/{slots,appointments,agenda/today}` —
booking, conflict rules, and the isolation between clinician/patient
views, built against the real `api.main.app` wiring."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from auth.security import create_access_token, hash_password
from core.db import get_session
from data.schemas import Patient, User

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="appt-clin@example.org") -> tuple[dict, str]:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Appt", "password": "password123"}
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


@pytest.fixture
async def patient_row(db_session):
    p = Patient(id="PAPPT1", name="Appt Patient", age=30, sex="M", medical_record_number="PT-PAPPT1")
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.fixture
async def patient_token(db_session, patient_row):
    user = User(
        id="user-pappt1",
        email="pappt1@example.org",
        name="Appt Patient",
        hashed_password=hash_password("password123"),
        role="patient",
        patient_id=patient_row.id,
    )
    db_session.add(user)
    await db_session.commit()
    return create_access_token(user.id)


async def _set_up_availability(client, headers):
    await client.post(
        "/api/scheduling/availability",
        json={"weekday": 0, "start_time": "09:00", "end_time": "11:00", "slot_minutes": 30},
        headers=headers,
    )


NEXT_MONDAY_ISO = "2026-08-24T09:00:00Z"  # 2026-08-24 is a Monday


async def test_book_appointment_happy_path(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        res = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": NEXT_MONDAY_ISO,
                "reason": "Follow-up",
            },
            headers=headers,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["status"] == "booked"
        assert body["end_at"] == "2026-08-24T09:30:00"


async def test_adjacent_appointments_do_not_conflict(client, patient_row, db_session):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        first = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        assert first.status_code == 201

        p2 = Patient(id="PAPPT2", name="Second", age=40, sex="F", medical_record_number="PT-PAPPT2")
        db_session.add(p2)
        await db_session.commit()

        second = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": p2.id,
                "start_at": "2026-08-24T09:30:00Z",
            },
            headers=headers,
        )
        assert second.status_code == 201


async def test_overlapping_booking_conflicts_409(client, patient_row, db_session):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )

        p2 = Patient(id="PAPPT3", name="Third", age=50, sex="M", medical_record_number="PT-PAPPT3")
        db_session.add(p2)
        await db_session.commit()

        res = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": p2.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        assert res.status_code == 409


async def test_patient_double_booking_across_clinicians_409(client, patient_row, db_session):
    async with client:
        headers_a, clinician_a = await _clinician(client, "appt-clin-a@example.org")
        headers_b, clinician_b = await _clinician(client, "appt-clin-b@example.org")
        await _set_up_availability(client, headers_a)
        await _set_up_availability(client, headers_b)

        first = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_a, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers_a,
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_b, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers_b,
        )
        assert second.status_code == 409


async def test_booking_outside_working_hours_422(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        res = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": "2026-08-24T20:00:00Z",
            },
            headers=headers,
        )
        assert res.status_code == 422


async def test_booking_in_the_past_422(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        res = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": "2020-01-01T09:00:00Z",
            },
            headers=headers,
        )
        assert res.status_code == 422


async def test_booking_beyond_horizon_422(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        res = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": "2027-06-01T09:00:00Z",
            },
            headers=headers,
        )
        assert res.status_code == 422


async def test_naive_datetime_rejected(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        res = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": "2026-08-24T09:00:00",
            },
            headers=headers,
        )
        assert res.status_code == 422


async def test_clinician_force_bypasses_working_hours(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        res = await client.post(
            "/api/scheduling/appointments?force=true",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": "2026-08-24T20:00:00Z",
            },
            headers=headers,
        )
        assert res.status_code == 201


async def test_patient_cannot_force_booking(client, patient_row, patient_token):
    async with client:
        headers_clin, clinician_id = await _clinician(client)
        res = await client.post(
            "/api/scheduling/appointments?force=true",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": "2026-08-24T20:00:00Z",
            },
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert res.status_code == 403


async def test_patient_cannot_book_for_another_patient(client, patient_token, db_session):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        other = Patient(id="PAPPT9", name="Other", age=25, sex="F", medical_record_number="PT-PAPPT9")
        db_session.add(other)
        await db_session.commit()

        res = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": other.id, "start_at": NEXT_MONDAY_ISO},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert res.status_code == 403


async def test_cancel_is_soft_and_frees_the_slot(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        booked = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        appt_id = booked.json()["id"]

        cancelled = await client.delete(
            f"/api/scheduling/appointments/{appt_id}?reason=no+longer+needed", headers=headers
        )
        assert cancelled.status_code == 204

        rebook = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        assert rebook.status_code == 201


async def test_patient_appointment_view_omits_notes(client, patient_row, patient_token):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)
        await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )

        as_patient = await client.get(
            "/api/scheduling/appointments", headers={"Authorization": f"Bearer {patient_token}"}
        )
        assert as_patient.status_code == 200
        assert len(as_patient.json()) == 1
        assert "notes" not in as_patient.json()[0]

        as_clinician = await client.get("/api/scheduling/appointments", headers=headers)
        assert "notes" in as_clinician.json()[0]


async def test_agenda_today_only_counts_todays_appointments(client, patient_row, monkeypatch):
    async with client:
        headers, clinician_id = await _clinician(client)
        res = await client.get("/api/scheduling/agenda/today", headers=headers)
        assert res.status_code == 200
        assert res.json()["count"] == 0
        assert res.json()["items"] == []


async def test_slots_endpoint_accessible_to_patient(client, patient_row, patient_token):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        res = await client.get(
            "/api/scheduling/slots",
            params={"clinician_id": clinician_id, "from": "2026-08-24", "to": "2026-08-25"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert res.status_code == 200
        assert len(res.json()["slots"]) == 4
