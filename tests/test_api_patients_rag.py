"""API tests for /api/patients, /api/rag, and /api/dashboard — read paths
backed by the isolated SQLite `db_session` fixture."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routers import dashboard as dashboard_router_module
from api.routers import patients as patients_router_module
from api.routers import rag as rag_router_module
from auth import router as auth_router_module
from core.db import get_session
from data.schemas import Patient
from tests.conftest import FakeOllamaClient

NOTE_EVENTS_PAYLOAD = {
    "events": [{"date": "2026-01-01", "type": "diagnosis", "title": "Test diagnosis", "detail": "detail"}]
}


@pytest.fixture
def app(db_session, monkeypatch):
    monkeypatch.setattr(patients_router_module, "_client", FakeOllamaClient())
    monkeypatch.setattr(dashboard_router_module, "_client", FakeOllamaClient())

    app = FastAPI()
    app.include_router(auth_router_module.router, prefix="/api/auth")
    app.include_router(patients_router_module.router, prefix="/api/patients")
    app.include_router(rag_router_module.router, prefix="/api/rag")
    app.include_router(dashboard_router_module.router, prefix="/api/dashboard")

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


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
        res = await client.get("/api/patients")
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1
        assert body[0]["id"] == "P001"
        assert "risk_level" in body[0]


@pytest.mark.asyncio
async def test_get_patient_detail_includes_full_fields(client, seeded_patient):
    async with client:
        res = await client.get("/api/patients/P001")
        assert res.status_code == 200
        body = res.json()
        assert body["medications"] == ["warfarin", "aspirin"]
        assert "timeline" in body
        assert "risk_flags" in body


@pytest.mark.asyncio
async def test_get_patient_risk_flags_reflect_labs_and_drug_interactions(client, seeded_patient):
    async with client:
        res = await client.get("/api/patients/P001")
        body = res.json()
        labels = {f["label"] for f in body["risk_flags"]}
        assert "Hyperkalemia" in labels
        assert any("warfarin" in label for label in labels)
        assert body["risk_level"] == "high"


@pytest.mark.asyncio
async def test_get_unknown_patient_404(client):
    async with client:
        res = await client.get("/api/patients/DOES-NOT-EXIST")
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_rag_search_returns_cited_results(client):
    async with client:
        res = await client.get("/api/rag/search", params={"q": "A1C goal type 2 diabetes"})
        assert res.status_code == 200
        body = res.json()
        assert body["results"]
        assert body["results"][0]["citation"]


@pytest.mark.asyncio
async def test_dashboard_stats_shape(client, seeded_patient):
    async with client:
        res = await client.get("/api/dashboard/stats")
        assert res.status_code == 200
        body = res.json()
        assert "kpis" in body
        assert "agents" in body
        assert "system" in body
        assert body["system"]["local_only"] is True


@pytest.mark.asyncio
async def test_add_clinical_note_extracts_entities_and_timeline(client, seeded_patient, monkeypatch):
    monkeypatch.setattr(
        patients_router_module,
        "_client",
        FakeOllamaClient(json_payloads=[NOTE_EVENTS_PAYLOAD]),
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
    monkeypatch.setattr(patients_router_module, "_client", FakeOllamaClient(json_payloads=[{"events": []}]))
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
