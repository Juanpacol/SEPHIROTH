"""PHI-access audit log: a row is written at each existing patient-data
read site, scoped to the right patient, with no route to mutate it."""

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
    patient = Patient(id="P910", name="Audit Target", age=50, sex="M", medical_record_number="PT-P910")
    db_session.add(patient)
    await db_session.commit()
    return patient


async def _clinician_headers(client, email="clinician@audit.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Audit", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def test_get_patient_writes_audit_row(client, seeded_patient):
    async with client:
        headers = await _clinician_headers(client)
        await client.get("/api/patients/P910", headers=headers)

        log = await client.get("/api/audit/access-log", headers=headers)
        assert log.status_code == 200
        rows = [r for r in log.json() if r["patient_id"] == "P910"]
        assert any(r["route"] == "/api/patients/{patient_id}" and r["method"] == "GET" for r in rows)


async def test_get_timeline_writes_audit_row(client, seeded_patient):
    async with client:
        headers = await _clinician_headers(client)
        await client.get("/api/patients/P910/timeline", headers=headers)

        log = (await client.get("/api/audit/access-log?patient_id=P910", headers=headers)).json()
        assert any(r["route"] == "/api/patients/{patient_id}/timeline" for r in log)


async def test_portal_reads_write_audit_row(client, seeded_patient):
    async with client:
        clinician_headers = await _clinician_headers(client)
        code = (await client.post("/api/patients/P910/invites", headers=clinician_headers)).json()["code"]
        claim = await client.post(
            "/api/auth/portal/claim",
            json={"code": code, "email": "patient@audit.org", "name": "Patient", "password": "password123"},
        )
        patient_headers = {"Authorization": f"Bearer {claim.json()['access_token']}"}

        await client.get("/api/portal/me", headers=patient_headers)
        await client.get("/api/portal/timeline", headers=patient_headers)
        await client.get("/api/portal/labs", headers=patient_headers)

        log = (await client.get("/api/audit/access-log?patient_id=P910", headers=clinician_headers)).json()
        routes = {r["route"] for r in log}
        assert "/api/portal/me" in routes
        assert "/api/portal/timeline" in routes
        assert "/api/portal/labs" in routes


async def test_access_log_is_clinician_only(client, seeded_patient):
    async with client:
        clinician_headers = await _clinician_headers(client)
        code = (await client.post("/api/patients/P910/invites", headers=clinician_headers)).json()["code"]
        claim = await client.post(
            "/api/auth/portal/claim",
            json={
                "code": code,
                "email": "patient2@audit.org",
                "name": "Patient",
                "password": "password123",
            },
        )
        patient_headers = {"Authorization": f"Bearer {claim.json()['access_token']}"}

        res = await client.get("/api/audit/access-log", headers=patient_headers)
        assert res.status_code == 403


async def test_no_mutation_route_exists_for_audit_log(client):
    async with client:
        headers = await _clinician_headers(client)
        # No POST/PATCH/DELETE route is registered under /api/audit at all.
        res = await client.post("/api/audit/access-log", headers=headers)
        assert res.status_code in (404, 405)
