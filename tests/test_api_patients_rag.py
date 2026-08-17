"""API tests for /api/patients, /api/rag, and /api/dashboard — read paths
backed by the isolated SQLite `db_session` fixture.

`/api/patients*` and `/api/dashboard/stats` used to have no auth at
all — anyone could list every patient's PHI. Phase A of the patient-portal
plan closes that with a router-level `dependencies=[Depends(get_current_user)]`
(mirrored here, since this file builds its own `FastAPI()` app rather than
importing `api.main`'s) — see `test_unauthenticated_*` below, the
regression lock for that fix."""

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from api.routers import dashboard as dashboard_router_module
from api.routers import patients as patients_router_module
from api.routers import rag as rag_router_module
from auth import router as auth_router_module
from auth.deps import get_current_user
from core.db import get_session
from data.schemas import Patient
from tests.conftest import FakeLLMClient

_authenticated = [Depends(get_current_user)]

NOTE_EVENTS_PAYLOAD = {
    "events": [{"date": "2026-01-01", "type": "diagnosis", "title": "Test diagnosis", "detail": "detail"}]
}


@pytest.fixture
def app(db_session, monkeypatch):
    import sephiroth.models.factory as factory_module

    monkeypatch.setattr(factory_module, "_client", FakeLLMClient())

    app = FastAPI()
    app.include_router(auth_router_module.router, prefix="/api/auth")
    app.include_router(patients_router_module.router, prefix="/api/patients", dependencies=_authenticated)
    app.include_router(rag_router_module.router, prefix="/api/rag")
    app.include_router(dashboard_router_module.router, prefix="/api/dashboard", dependencies=_authenticated)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


CREDS = {"email": "clinician@example.org", "name": "Dr. Test", "password": "password123"}


async def _auth_headers(client) -> dict:
    res = await client.post("/api/auth/register", json=CREDS)
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def seeded_patient(db_session):
    patient = Patient(
        id="P001",
        name="Test Patient",
        age=52,
        sex="M",
        medical_record_number="PT-00001",
        conditions=["Hyperkalemia risk"],
        medications=["warfarin", "aspirin"],
        allergies=[],
        lab_results={"potassium": "6.0 mEq/L"},
    )
    db_session.add(patient)
    await db_session.commit()
    return patient


@pytest.mark.asyncio
async def test_list_patients_returns_summary(client, seeded_patient):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/patients", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1
        assert body[0]["id"] == "P001"
        assert "risk_level" in body[0]


@pytest.mark.asyncio
async def test_create_patient_returns_full_record_with_empty_timeline(client):
    """No test exercised the successful creation path before — it's what
    caught a real Postgres-only bug (`patient.timeline = []` after
    `commit()` triggered an implicit lazy-load `MissingGreenlet` under
    asyncpg; SQLite's driver tolerated it silently, so this suite never
    saw it fail). The `session.refresh(..., attribute_names=["timeline"])`
    fix should return the same shape on both dialects."""
    async with client:
        headers = await _auth_headers(client)
        res = await client.post(
            "/api/patients", json={"name": "New Patient", "age": 61, "sex": "F"}, headers=headers
        )
        assert res.status_code == 201
        body = res.json()
        assert body["name"] == "New Patient"
        assert body["timeline"] == []
        assert body["medical_record_number"]


@pytest.mark.asyncio
async def test_get_patient_detail_includes_full_fields(client, seeded_patient):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/patients/P001", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["medications"] == ["warfarin", "aspirin"]
        assert "timeline" in body
        assert "risk_flags" in body


@pytest.mark.asyncio
async def test_get_patient_risk_flags_reflect_labs_and_drug_interactions(client, seeded_patient):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/patients/P001", headers=headers)
        body = res.json()
        labels = {f["label"] for f in body["risk_flags"]}
        assert "Hyperkalemia" in labels
        assert any("warfarin" in label for label in labels)
        assert body["risk_level"] == "high"


@pytest.mark.asyncio
async def test_get_unknown_patient_404(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/patients/DOES-NOT-EXIST", headers=headers)
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_cannot_list_patients(client, seeded_patient):
    """Regression lock: `/api/patients` used to have no auth at all — any
    unauthenticated caller could list every patient's PHI."""
    async with client:
        res = await client.get("/api/patients")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_cannot_create_patient(client):
    async with client:
        res = await client.post("/api/patients", json={"name": "X", "age": 30, "sex": "M"})
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_cannot_get_patient_detail(client, seeded_patient):
    async with client:
        res = await client.get("/api/patients/P001")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_cannot_get_patient_timeline(client, seeded_patient):
    async with client:
        res = await client.get("/api/patients/P001/timeline")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_cannot_read_dashboard_stats(client):
    """Regression lock: `/api/dashboard/stats` used to have no auth at
    all — any unauthenticated caller could read aggregate PHI (patient
    counts, high-risk counts derived from every patient's labs/meds)."""
    async with client:
        res = await client.get("/api/dashboard/stats")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_rag_search_returns_cited_results(client):
    async with client:
        register = await client.post(
            "/api/auth/register",
            json={"email": "rag@example.org", "name": "Dr. Rag", "password": "password123"},
        )
        token = register.json()["access_token"]

        res = await client.get(
            "/api/rag/search",
            params={"q": "A1C goal type 2 diabetes"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["results"]
        assert body["results"][0]["citation"]


@pytest.mark.asyncio
async def test_rag_search_requires_auth(client):
    """DEBT-004 (docs/specs/SPEC-002-tool-runtime.md): search_pubmed makes a
    real network call per request, so an unauthenticated search endpoint is
    also an open door to consuming that quota."""
    async with client:
        res = await client.get("/api/rag/search", params={"q": "A1C goal type 2 diabetes"})
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_stats_shape(client, seeded_patient):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/dashboard/stats", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "kpis" in body
        assert "agents" in body
        assert "system" in body
        assert body["system"]["local_only"] is False


@pytest.mark.asyncio
async def test_add_clinical_note_extracts_entities_and_timeline(client, seeded_patient, monkeypatch):
    import sephiroth.models.factory as factory_module

    monkeypatch.setattr(
        factory_module,
        "_client",
        FakeLLMClient(json_payloads=[NOTE_EVENTS_PAYLOAD]),
    )
    async with client:
        register = await client.post(
            "/api/auth/register",
            json={"email": "note@example.org", "name": "Dr. Note", "password": "password123"},
        )
        token = register.json()["access_token"]

        res = await client.post(
            "/api/patients/P001/notes",
            json={"content": "Patient reports fatigue and was started on metformin."},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["entities_found"] >= 1
        assert len(body["events_added"]) == 1
        assert body["events_added"][0]["title"] == "Test diagnosis"


@pytest.mark.asyncio
async def test_add_clinical_note_requires_auth(client, seeded_patient):
    async with client:
        res = await client.post(
            "/api/patients/P001/notes", json={"content": "Some clinical note content here."}
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_add_clinical_note_unknown_patient_404(client, monkeypatch):
    import sephiroth.models.factory as factory_module

    monkeypatch.setattr(factory_module, "_client", FakeLLMClient(json_payloads=[{"events": []}]))
    async with client:
        register = await client.post(
            "/api/auth/register",
            json={"email": "note2@example.org", "name": "Dr. Note", "password": "password123"},
        )
        token = register.json()["access_token"]
        res = await client.post(
            "/api/patients/DOES-NOT-EXIST/notes",
            json={"content": "Some clinical note content here."},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404
