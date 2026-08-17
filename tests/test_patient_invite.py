"""Patient-portal invite/claim flow — the only way a patient account is
created. No self-registration path exists; a clinician issues a one-time
code bound to an existing chart, and the patient redeems it."""

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


@pytest.fixture
async def seeded_patient(db_session):
    patient = Patient(
        id="P900",
        name="Invite Target",
        age=45,
        sex="F",
        medical_record_number="PT-P900",
    )
    db_session.add(patient)
    await db_session.commit()
    return patient


async def _clinician_headers(client, email="clinician@invite.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Invite", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def test_invite_claim_happy_path(client, seeded_patient):
    async with client:
        headers = await _clinician_headers(client)
        invite_res = await client.post("/api/patients/P900/invites", headers=headers)
        assert invite_res.status_code == 201
        code = invite_res.json()["code"]

        claim_res = await client.post(
            "/api/auth/portal/claim",
            json={
                "code": code,
                "email": "patient@example.org",
                "name": "Real Patient",
                "password": "password123",
            },
        )
        assert claim_res.status_code == 201
        body = claim_res.json()
        assert body["user"]["role"] == "patient"
        assert body["user"]["patient_id"] == "P900"

        me_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me_res.json()["role"] == "patient"
        assert me_res.json()["patient_id"] == "P900"


async def test_invite_cannot_be_redeemed_twice(client, seeded_patient):
    async with client:
        headers = await _clinician_headers(client)
        code = (await client.post("/api/patients/P900/invites", headers=headers)).json()["code"]

        first = {"code": code, "email": "p1@example.org", "name": "P1", "password": "password123"}
        assert (await client.post("/api/auth/portal/claim", json=first)).status_code == 201

        second = {"code": code, "email": "p2@example.org", "name": "P2", "password": "password123"}
        res = await client.post("/api/auth/portal/claim", json=second)
        assert res.status_code == 400


async def test_expired_invite_rejected(client, seeded_patient, db_session):
    from datetime import datetime, timedelta, timezone

    from data.schemas import PatientInvite

    async with client:
        headers = await _clinician_headers(client)
        code = (await client.post("/api/patients/P900/invites", headers=headers)).json()["code"]

        invite_id = code.split(".")[0]
        invite = await db_session.get(PatientInvite, invite_id)
        invite.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        await db_session.commit()

        res = await client.post(
            "/api/auth/portal/claim",
            json={"code": code, "email": "late@example.org", "name": "Late", "password": "password123"},
        )
        assert res.status_code == 400


async def test_wrong_secret_rejected_with_generic_error(client, seeded_patient):
    async with client:
        headers = await _clinician_headers(client)
        code = (await client.post("/api/patients/P900/invites", headers=headers)).json()["code"]
        invite_id = code.split(".")[0]
        bad_code = f"{invite_id}.wrong-secret-value"

        res = await client.post(
            "/api/auth/portal/claim",
            json={"code": bad_code, "email": "x@example.org", "name": "X", "password": "password123"},
        )
        assert res.status_code == 400
        assert res.json()["detail"] == "Invalid or expired claim code"


async def test_unknown_invite_id_same_generic_error(client):
    async with client:
        res = await client.post(
            "/api/auth/portal/claim",
            json={
                "code": "does-not-exist.secret",
                "email": "x2@example.org",
                "name": "X2",
                "password": "password123",
            },
        )
        assert res.status_code == 400
        assert res.json()["detail"] == "Invalid or expired claim code"


async def test_second_claim_against_already_claimed_patient_rejected(client, seeded_patient):
    """The unique FK on User.patient_id: even a second, freshly-issued
    invite for the same patient can't produce a second login."""
    async with client:
        headers = await _clinician_headers(client)
        code1 = (await client.post("/api/patients/P900/invites", headers=headers)).json()["code"]
        await client.post(
            "/api/auth/portal/claim",
            json={"code": code1, "email": "first@example.org", "name": "First", "password": "password123"},
        )

        code2 = (await client.post("/api/patients/P900/invites", headers=headers)).json()["code"]
        res = await client.post(
            "/api/auth/portal/claim",
            json={
                "code": code2,
                "email": "second@example.org",
                "name": "Second",
                "password": "password123",
            },
        )
        assert res.status_code == 400


async def test_create_invite_requires_clinician(client, seeded_patient):
    async with client:
        res = await client.post("/api/patients/P900/invites")
        assert res.status_code == 401


async def test_create_invite_unknown_patient_404(client):
    async with client:
        headers = await _clinician_headers(client)
        res = await client.post("/api/patients/DOES-NOT-EXIST/invites", headers=headers)
        assert res.status_code == 404


async def test_claim_rejects_extra_fields(client, seeded_patient):
    async with client:
        headers = await _clinician_headers(client)
        code = (await client.post("/api/patients/P900/invites", headers=headers)).json()["code"]
        res = await client.post(
            "/api/auth/portal/claim",
            json={
                "code": code,
                "email": "extra@example.org",
                "name": "Extra",
                "password": "password123",
                "role": "clinician",
            },
        )
        assert res.status_code == 422
