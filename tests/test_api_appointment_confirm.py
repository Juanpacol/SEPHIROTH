"""`POST /api/scheduling/appointments/{id}/confirm` (SPEC-012)."""

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


NEXT_MONDAY_ISO = f"{_next_monday()}T09:00:00Z"


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="confirm-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Confirm", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def patient_row(db_session):
    p = Patient(id="PCONF1", name="Confirm Patient", age=35, sex="F", medical_record_number="PT-PCONF1")
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.fixture
async def patient_headers(db_session, patient_row):
    user = User(
        id="user-pconf1",
        email="pconf1@example.org",
        name="Confirm Patient",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id=patient_row.id,
    )
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def test_patient_can_confirm_own_appointment(client, patient_row, patient_headers):
    clin_headers = await _clinician(client)
    me = await client.get("/api/auth/me", headers=clin_headers)
    clinician_id = me.json()["id"]
    await client.post(
        "/api/scheduling/availability",
        json={"weekday": 0, "start_time": "09:00", "end_time": "11:00", "slot_minutes": 30},
        headers=clin_headers,
    )
    book_res = await client.post(
        "/api/scheduling/appointments",
        json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
        headers=clin_headers,
    )
    appt_id = book_res.json()["id"]

    confirm_res = await client.post(
        f"/api/scheduling/appointments/{appt_id}/confirm", headers=patient_headers
    )

    assert confirm_res.status_code == 200
    assert confirm_res.json()["confirmed_at"] is not None


async def test_confirm_is_idempotent(client, patient_row, patient_headers):
    clin_headers = await _clinician(client)
    me = await client.get("/api/auth/me", headers=clin_headers)
    clinician_id = me.json()["id"]
    await client.post(
        "/api/scheduling/availability",
        json={"weekday": 0, "start_time": "09:00", "end_time": "11:00", "slot_minutes": 30},
        headers=clin_headers,
    )
    book_res = await client.post(
        "/api/scheduling/appointments",
        json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
        headers=clin_headers,
    )
    appt_id = book_res.json()["id"]

    first = await client.post(f"/api/scheduling/appointments/{appt_id}/confirm", headers=patient_headers)
    second = await client.post(f"/api/scheduling/appointments/{appt_id}/confirm", headers=patient_headers)

    assert first.json()["confirmed_at"] == second.json()["confirmed_at"]


async def test_patient_cannot_confirm_another_patients_appointment(client, patient_row, db_session):
    clin_headers = await _clinician(client)
    me = await client.get("/api/auth/me", headers=clin_headers)
    clinician_id = me.json()["id"]
    await client.post(
        "/api/scheduling/availability",
        json={"weekday": 0, "start_time": "09:00", "end_time": "11:00", "slot_minutes": 30},
        headers=clin_headers,
    )
    book_res = await client.post(
        "/api/scheduling/appointments",
        json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
        headers=clin_headers,
    )
    appt_id = book_res.json()["id"]

    other_patient = Patient(
        id="PCONF2", name="Other Patient", age=40, sex="M", medical_record_number="PT-PCONF2"
    )
    db_session.add(other_patient)
    other_user = User(
        id="user-pconf2",
        email="pconf2@example.org",
        name="Other Patient",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id="PCONF2",
    )
    db_session.add(other_user)
    await db_session.commit()
    other_headers = {"Authorization": f"Bearer {create_access_token(other_user.id)}"}

    res = await client.post(f"/api/scheduling/appointments/{appt_id}/confirm", headers=other_headers)
    assert res.status_code == 404
