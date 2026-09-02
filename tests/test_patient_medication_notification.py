"""Prescribing a medication (`POST /api/patients/{id}/medications`) is the
only place `Patient.medications` changes after patient creation, and it
notifies the owning patient's portal login, if one exists -- same
"real endpoint, not just a script" contract as result-share notifications
(see test_result_share_notification.py)."""

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


async def _clinician(client, email="med-notif-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Rx", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def patient_with_no_meds(db_session):
    patient = Patient(
        id="PMEDNOTIF1", name="Med Notif Patient", age=52, sex="M", medical_record_number="PT-PMN1"
    )
    db_session.add(patient)
    await db_session.commit()
    return patient


@pytest.fixture
async def patient_login(db_session, patient_with_no_meds):
    user = User(
        id="user-pmednotif1",
        email="pmednotif1@example.org",
        name="Med Notif Patient",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id=patient_with_no_meds.id,
    )
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def test_prescribe_medication_appends_and_notifies_patient_login(
    client, patient_with_no_meds, patient_login
):
    async with client:
        clinician_headers = await _clinician(client)
        res = await client.post(
            f"/api/patients/{patient_with_no_meds.id}/medications",
            json={"name": "Metformin", "dosage": "500mg"},
            headers=clinician_headers,
        )
        assert res.status_code == 201
        assert res.json()["medications"] == ["Metformin 500mg"]

        notifications = await client.get("/api/notifications", headers=patient_login)
        body = notifications.json()
        assert len(body) == 1
        assert body[0]["type"] == "medication_prescribed"
        assert "Metformin 500mg" in body[0]["message"]


async def test_prescribe_medication_without_portal_login_does_not_error(client, patient_with_no_meds):
    """No portal login exists for this patient yet -- prescribing must
    still succeed; there's simply no one to notify."""
    async with client:
        clinician_headers = await _clinician(client)
        res = await client.post(
            f"/api/patients/{patient_with_no_meds.id}/medications",
            json={"name": "Lisinopril", "dosage": "10mg"},
            headers=clinician_headers,
        )
        assert res.status_code == 201
        assert res.json()["medications"] == ["Lisinopril 10mg"]


async def test_prescribe_medication_appends_without_clobbering_existing(client, db_session, patient_login):
    patient = await db_session.get(Patient, "PMEDNOTIF1")
    patient.medications = ["Existing Med 20mg"]
    await db_session.commit()

    async with client:
        clinician_headers = await _clinician(client)
        res = await client.post(
            f"/api/patients/{patient.id}/medications",
            json={"name": "Metformin", "dosage": "500mg"},
            headers=clinician_headers,
        )
        assert res.status_code == 201
        assert res.json()["medications"] == ["Existing Med 20mg", "Metformin 500mg"]


async def test_prescribe_medication_requires_name(client, patient_with_no_meds):
    async with client:
        clinician_headers = await _clinician(client)
        res = await client.post(
            f"/api/patients/{patient_with_no_meds.id}/medications",
            json={"name": "", "dosage": "10mg"},
            headers=clinician_headers,
        )
        assert res.status_code == 422


async def test_prescribe_medication_unknown_patient_404s(client):
    async with client:
        clinician_headers = await _clinician(client)
        res = await client.post(
            "/api/patients/NOPE/medications",
            json={"name": "Aspirin", "dosage": "81mg"},
            headers=clinician_headers,
        )
        assert res.status_code == 404
