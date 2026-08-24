"""Security regression: a patient must not be able to book against an
inactive (or synthetic-system) clinician account by guessing its id.

`system-workflow` (`platform/core/db.py`) is the concrete real-world
instance -- `role="clinician"`, `is_active=False`, a hardcoded id shipped
in every deployment. Before this fix, `POST /api/scheduling/appointments`
(and `/series`, `/waitlist`) resolved a clinician by `role` alone."""

from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from auth.security import create_access_token, hash_password
from core.db import SYSTEM_WORKFLOW_USER_ID, get_session
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


@pytest.fixture
async def patient_headers(db_session):
    p = Patient(id="PSEC1", name="Security Patient", age=30, sex="F", medical_record_number="PT-PSEC1")
    db_session.add(p)
    user = User(
        id="user-psec1",
        email="psec1@example.org",
        name="Security Patient",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id=p.id,
    )
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
async def inactive_clinician(db_session):
    """Mirrors the exact real-world shape of `system-workflow` --
    id doesn't have to match, only `role`/`is_active`."""
    u = User(
        id="inactive-clin-1",
        email="inactive@example.org",
        name="Deactivated Clinician",
        hashed_password="",
        role="clinician",
        is_active=False,
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def test_cannot_book_against_inactive_clinician(
    client, patient_headers, patient_row_id, inactive_clinician
):
    res = await client.post(
        "/api/scheduling/appointments",
        json={
            "clinician_id": inactive_clinician.id,
            "patient_id": patient_row_id,
            "start_at": NEXT_MONDAY_ISO,
        },
        headers=patient_headers,
    )
    assert res.status_code == 404


async def test_cannot_book_against_system_workflow_user_id(
    client, patient_headers, patient_row_id, db_session
):
    """The concrete exploit: system-workflow's id is a hardcoded constant
    shipped in every deployment, guessable without any information
    disclosure. It doesn't need to exist in this test's DB -- a 404 for
    a nonexistent/inactive clinician id looks identical to the caller,
    which is exactly the point (no oracle for "this account exists but
    is disabled")."""
    res = await client.post(
        "/api/scheduling/appointments",
        json={
            "clinician_id": SYSTEM_WORKFLOW_USER_ID,
            "patient_id": patient_row_id,
            "start_at": NEXT_MONDAY_ISO,
        },
        headers=patient_headers,
    )
    assert res.status_code == 404


@pytest.fixture
async def patient_row_id(patient_headers, db_session):
    # patient_headers already inserted the patient as "PSEC1" -- fetch it
    # back so this fixture composes cleanly for tests that need the id.
    return "PSEC1"


async def test_series_booking_also_rejects_inactive_clinician(
    client, patient_headers, patient_row_id, inactive_clinician
):
    res = await client.post(
        "/api/scheduling/series",
        json={
            "clinician_id": inactive_clinician.id,
            "patient_id": patient_row_id,
            "start_at": NEXT_MONDAY_ISO,
            "frequency": "weekly",
            "occurrence_count": 2,
        },
        headers=patient_headers,
    )
    assert res.status_code == 404


async def test_waitlist_also_rejects_inactive_clinician(client, patient_headers, inactive_clinician):
    res = await client.post(
        "/api/scheduling/waitlist",
        json={
            "clinician_id": inactive_clinician.id,
            "window_start": NEXT_MONDAY_ISO,
            "window_end": f"{_next_monday()}T17:00:00Z",
        },
        headers=patient_headers,
    )
    assert res.status_code == 404
