"""API tests for /api/patients, /api/rag, and /api/dashboard — read paths
backed by the isolated SQLite `db_session` fixture.

`/api/patients*` and `/api/dashboard/stats` used to have no auth at
all — anyone could list every patient's PHI. Phase A of the patient-portal
plan closes that with a router-level `dependencies=[Depends(get_current_user)]`
(mirrored here, since this file builds its own `FastAPI()` app rather than
importing `api.main`'s) — see `test_unauthenticated_*` below, the
regression lock for that fix."""

from contextlib import asynccontextmanager

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

    # `/patients/{id}/notes` (and `/notes/upload`) persist via `SessionLocal()`
    # directly, not the injectable dependency — so a pooled connection isn't
    # held idle-in-transaction across the LLM entity/event extraction calls.
    @asynccontextmanager
    async def _session_cm():
        yield db_session

    monkeypatch.setattr(patients_router_module, "SessionLocal", lambda: _session_cm())

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
async def test_list_patients_sort_risk_puts_high_risk_first(client, seeded_patient, db_session):
    """Default order is alphabetical (seeded_patient's "Test Patient" would
    sort after "Aaron Low Risk"); `sort=risk` must reorder to put the
    high-risk patient first regardless of name."""
    low_risk = Patient(
        id="P002",
        name="Aaron Low Risk",
        age=30,
        sex="F",
        medical_record_number="PT-00002",
        conditions=[],
        medications=[],
        allergies=[],
        lab_results={},
    )
    db_session.add(low_risk)
    await db_session.commit()

    async with client:
        headers = await _auth_headers(client)

        default_res = await client.get("/api/patients", headers=headers)
        assert [p["id"] for p in default_res.json()] == ["P002", "P001"]

        risk_res = await client.get("/api/patients?sort=risk", headers=headers)
        body = risk_res.json()
        assert [p["id"] for p in body] == ["P001", "P002"]
        assert body[0]["risk_level"] == "high"
        assert body[1]["risk_level"] == "low"


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
async def test_add_timeline_event_appears_in_patient_detail(client, seeded_patient):
    async with client:
        headers = await _auth_headers(client)
        res = await client.post(
            f"/api/patients/{seeded_patient.id}/timeline",
            json={
                "type": "imaging",
                "title": "Chest X-ray reviewed",
                "detail": "Bilateral infiltrates visible.",
            },
            headers=headers,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["title"] == "Chest X-ray reviewed"
        assert body["type"] == "imaging"
        assert body["ai_generated"] is True

        detail_res = await client.get(f"/api/patients/{seeded_patient.id}", headers=headers)
        titles = [e["title"] for e in detail_res.json()["timeline"]]
        assert "Chest X-ray reviewed" in titles


@pytest.mark.asyncio
async def test_add_timeline_event_duplicate_date_and_title_409s(client, seeded_patient):
    async with client:
        headers = await _auth_headers(client)
        payload = {"date": "2026-01-01", "title": "Chest X-ray reviewed", "detail": "First."}
        first = await client.post(
            f"/api/patients/{seeded_patient.id}/timeline", json=payload, headers=headers
        )
        assert first.status_code == 201

        second = await client.post(
            f"/api/patients/{seeded_patient.id}/timeline",
            json={**payload, "detail": "Second, different detail."},
            headers=headers,
        )
        assert second.status_code == 409


@pytest.mark.asyncio
async def test_add_timeline_event_requires_auth(client, seeded_patient):
    async with client:
        res = await client.post(
            f"/api/patients/{seeded_patient.id}/timeline", json={"title": "Chest X-ray reviewed"}
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_evidence_categories_lists_every_category_with_counts(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/rag/categories", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert len(body) > 1
        assert all({"slug", "label", "count"} <= set(c.keys()) for c in body)
        assert sum(c["count"] for c in body) == 37  # len(SEED_GUIDELINES)
        # Sorted by label, not slug — "Cancer Screening" before "Cardiovascular".
        labels = [c["label"] for c in body]
        assert labels == sorted(labels)


@pytest.mark.asyncio
async def test_evidence_categories_requires_auth(client):
    async with client:
        res = await client.get("/api/rag/categories")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_evidence_by_category_returns_excerpts(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/rag/categories/cardiovascular", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert len(body) > 1
        assert all(
            {"id", "title", "organization", "year", "excerpt", "citation"} <= set(item.keys())
            for item in body
        )


@pytest.mark.asyncio
async def test_evidence_by_category_unknown_category_404s(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/rag/categories/not-a-real-category", headers=headers)
        assert res.status_code == 404


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
    """`seeded_patient` (potassium 6.0 -> Hyperkalemia, warfarin+aspirin ->
    a major interaction) is high-risk, so it must show up in
    `critical_patients` — this is the dashboard's whole point now: which
    patients need attention, not aggregate counts."""
    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/dashboard/stats", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["critical_count"] == 1
        assert body["at_risk_count"] == 1
        assert len(body["critical_patients"]) == 1
        critical = body["critical_patients"][0]
        assert critical["id"] == "P001"
        assert critical["risk_level"] == "high"
        assert critical["flag_count"] >= 2
        assert critical["top_flag"]


@pytest.mark.asyncio
async def test_dashboard_stats_excludes_low_risk_patients(client, seeded_patient, db_session):
    low_risk = Patient(
        id="P003",
        name="No Flags Patient",
        age=40,
        sex="F",
        medical_record_number="PT-00003",
        conditions=[],
        medications=[],
        allergies=[],
        lab_results={},
    )
    db_session.add(low_risk)
    await db_session.commit()

    async with client:
        headers = await _auth_headers(client)
        res = await client.get("/api/dashboard/stats", headers=headers)
        body = res.json()
        assert body["at_risk_count"] == 1
        assert all(p["id"] != "P003" for p in body["critical_patients"])


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
