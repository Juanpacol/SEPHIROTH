"""Patient portal read endpoints — `/api/portal/{me,timeline,labs}` — and
the two edge-case dependency branches Phase B introduces:
`require_clinician_for_registration`'s flag-off path, and
`current_patient_record`'s 404 when the bound chart no longer exists."""

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from auth.security import create_access_token, hash_password
from core.config import settings
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


@pytest.fixture
async def patient_token(db_session):
    patient = Patient(
        id="PPORTAL1",
        name="Portal Patient",
        age=33,
        sex="F",
        medical_record_number="PT-PPORTAL1",
        conditions=["Hypertension"],
        medications=["lisinopril"],
        allergies=["penicillin"],
        lab_results={"a1c": "6.1%"},
    )
    db_session.add(patient)
    db_session.add_all(
        [
            TimelineEvent(
                patient_id="PPORTAL1",
                date=date(2026, 1, 1),
                type="lab",
                title="AI note",
                ai_generated=True,
            ),
            TimelineEvent(
                patient_id="PPORTAL1",
                date=date(2026, 1, 2),
                type="diagnosis",
                title="Clinician note",
                ai_generated=False,
            ),
        ]
    )
    user = User(
        id="user-pportal1",
        email="portal1@example.org",
        name="Portal Patient",
        hashed_password=hash_password("password123"),
        role="patient",
        patient_id="PPORTAL1",
    )
    db_session.add(user)
    await db_session.commit()
    return create_access_token(user.id)


async def test_portal_me_returns_chart_fields_not_risk(client, patient_token):
    async with client:
        res = await client.get("/api/portal/me", headers={"Authorization": f"Bearer {patient_token}"})
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == "PPORTAL1"
        assert body["conditions"] == ["Hypertension"]
        assert "risk_level" not in body
        assert "risk_flags" not in body


async def test_portal_timeline_excludes_ai_generated_events(client, patient_token):
    async with client:
        res = await client.get("/api/portal/timeline", headers={"Authorization": f"Bearer {patient_token}"})
        assert res.status_code == 200
        titles = [e["title"] for e in res.json()["events"]]
        assert titles == ["Clinician note"]


async def test_portal_timeline_event_type_filter(client, patient_token):
    async with client:
        res = await client.get(
            "/api/portal/timeline",
            params={"event_type": "diagnosis"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert [e["type"] for e in res.json()["events"]] == ["diagnosis"]

        res_empty = await client.get(
            "/api/portal/timeline",
            params={"event_type": "lab"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert res_empty.json()["events"] == []


async def test_portal_labs(client, patient_token):
    async with client:
        res = await client.get("/api/portal/labs", headers={"Authorization": f"Bearer {patient_token}"})
        assert res.status_code == 200
        assert res.json()["lab_results"] == {"a1c": "6.1%"}


async def test_portal_404_when_bound_chart_deleted(client, db_session):
    """`current_patient_record` must 404, not 500, if the chart a portal
    login is bound to has since been deleted."""
    user = User(
        id="user-orphan",
        email="orphan@example.org",
        name="Orphan",
        hashed_password=hash_password("password123"),
        role="patient",
        patient_id="DOES-NOT-EXIST",
    )
    db_session.add(user)
    await db_session.commit()
    token = create_access_token(user.id)

    async with client:
        res = await client.get("/api/portal/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 404


async def test_register_bootstrap_flag_off_requires_clinician_token(client, monkeypatch):
    """With bootstrap registration disabled, an unauthenticated caller
    can no longer create the first account for free."""
    monkeypatch.setattr(settings, "allow_bootstrap_registration", False)
    async with client:
        res = await client.post(
            "/api/auth/register",
            json={"email": "nope@example.org", "name": "Nope", "password": "password123"},
        )
        assert res.status_code == 401


async def test_register_bootstrap_flag_off_patient_token_rejected(client, patient_token, monkeypatch):
    monkeypatch.setattr(settings, "allow_bootstrap_registration", False)
    async with client:
        res = await client.post(
            "/api/auth/register",
            json={"email": "nope2@example.org", "name": "Nope", "password": "password123"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert res.status_code == 403


async def test_register_bootstrap_flag_off_clinician_token_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_bootstrap_registration", True)
    async with client:
        first = await client.post(
            "/api/auth/register",
            json={"email": "first-clinician@example.org", "name": "Dr. First", "password": "password123"},
        )
        headers = {"Authorization": f"Bearer {first.json()['access_token']}"}

        monkeypatch.setattr(settings, "allow_bootstrap_registration", False)
        res = await client.post(
            "/api/auth/register",
            json={"email": "second-clinician@example.org", "name": "Dr. Second", "password": "password123"},
            headers=headers,
        )
        assert res.status_code == 201
