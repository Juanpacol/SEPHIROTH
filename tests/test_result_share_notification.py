"""Creating a result share notifies the owning patient's portal login, if
one exists."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from auth.security import create_access_token, hash_password
from core.db import get_session
from data.schemas import Patient, TimelineEvent, User

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="share-notif-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Notif", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def patient_with_lab_event(db_session):
    from datetime import date

    patient = Patient(
        id="PSHARENOTIF1", name="Notif Patient", age=40, sex="F", medical_record_number="PT-PSN1"
    )
    db_session.add(patient)
    event = TimelineEvent(patient_id=patient.id, date=date(2026, 1, 1), type="lab", title="CBC", detail="")
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return patient, event


@pytest.fixture
async def patient_login(db_session, patient_with_lab_event):
    patient, _ = patient_with_lab_event
    user = User(
        id="user-psharenotif1",
        email="psharenotif1@example.org",
        name="Notif Patient",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id=patient.id,
    )
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def test_create_share_notifies_patient_login(client, patient_with_lab_event, patient_login):
    patient, event = patient_with_lab_event
    async with client:
        clinician_headers = await _clinician(client)
        res = await client.post(
            "/api/results/shares",
            json={"patient_id": patient.id, "timeline_event_id": event.id},
            headers=clinician_headers,
        )
        assert res.status_code == 201

        notifications = await client.get("/api/notifications", headers=patient_login)
        assert len(notifications.json()) == 1
        assert notifications.json()[0]["type"] == "result_shared"


async def test_create_share_without_patient_login_does_not_error(client, patient_with_lab_event):
    """No portal login exists for this patient yet — sharing must still
    succeed; there's simply no one to notify."""
    patient, event = patient_with_lab_event
    async with client:
        clinician_headers = await _clinician(client)
        res = await client.post(
            "/api/results/shares",
            json={"patient_id": patient.id, "timeline_event_id": event.id},
            headers=clinician_headers,
        )
        assert res.status_code == 201
