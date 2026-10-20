"""Recording a lab result from the patient chart (AB#31).

The form asks the server three things the intake route did not: which tests it
offers (with unit and range), how a value would be classified before saving, and
whether a value is possible at all. Plus the unit surviving into the patient
snapshot.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.routers import result_reviews as reviews_module
from api.services import result_service as svc
from auth import router as auth_router_module
from auth.security import create_access_token, hash_password
from core.db import get_session
from data.schemas import Patient, PhiAccessLog, User
from sephiroth.clinical.results import LAB_PLAUSIBLE, LAB_UNITS, REFERENCE_RANGES, lab_catalog

pytestmark = pytest.mark.asyncio

CREDS = {"email": "form-doc@example.org", "name": "Dra. Form", "password": "password123"}


@pytest.fixture
def app(db_session):
    api = FastAPI()
    api.include_router(auth_router_module.router, prefix="/api/auth")
    api.include_router(reviews_module.router, prefix="/api/results")

    async def override_session():
        yield db_session

    api.dependency_overrides[get_session] = override_session
    return api


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def headers(client):
    token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def patient(db_session):
    row = Patient(id="PFORM1", name="Ana Gómez", age=61, sex="F", medical_record_number="MRN-PFORM1")
    db_session.add(row)
    await db_session.commit()
    return row


def _body(patient, **extra):
    body = {"patient_id": patient.id, "test_name": "potassium", "value": 3.4, "unit": "mEq/L"}
    body.update(extra)
    return body


class TestCatalog:
    async def test_every_test_has_a_unit_a_range_and_a_plausible_span(self):
        assert set(LAB_UNITS) == set(LAB_PLAUSIBLE) == set(REFERENCE_RANGES)

    async def test_the_endpoint_lists_name_unit_and_range(self, client, headers):
        res = await client.get("/api/results/labs/catalog", headers=headers)

        assert res.status_code == 200
        tests = {t["test_name"]: t for t in res.json()["tests"]}
        assert tests["potassium"]["unit"] == "mEq/L"
        assert (
            tests["potassium"]["reference_low"],
            tests["potassium"]["reference_high"],
        ) == REFERENCE_RANGES["potassium"]
        assert len(tests) == len(lab_catalog())

    async def test_it_needs_a_clinician(self, client):
        assert (await client.get("/api/results/labs/catalog")).status_code in (401, 403)

    async def test_a_patient_account_is_refused(self, client, db_session, patient):
        user = User(
            id=f"u-{uuid4().hex[:6]}",
            email="pat-form@example.org",
            name="Paciente",
            hashed_password=await hash_password("password123"),
            role="patient",
            patient_id=patient.id,
        )
        db_session.add(user)
        await db_session.commit()
        pat = {"Authorization": f"Bearer {create_access_token(user.id)}"}

        assert (await client.get("/api/results/labs/catalog", headers=pat)).status_code == 403
        assert (
            await client.post("/api/results/labs/preview", json=_body(patient), headers=pat)
        ).status_code == 403
        assert (await client.post("/api/results/labs", json=_body(patient), headers=pat)).status_code == 403


class TestPreview:
    async def test_it_classifies_without_saving(self, client, headers, patient, db_session):
        res = await client.post(
            "/api/results/labs/preview", json={"test_name": "potassium", "value": 6.5}, headers=headers
        )

        assert res.status_code == 200
        body = res.json()
        assert body["severity"] == "critical"
        assert body["reason"]
        inbox = (await client.get("/api/results/inbox", headers=headers)).json()
        assert not (inbox["items"] if isinstance(inbox, dict) else inbox)

    async def test_it_agrees_with_what_saving_then_records(self, client, headers, patient):
        for value in (3.4, 4.2, 6.5):
            preview = (
                await client.post(
                    "/api/results/labs/preview",
                    json={"test_name": "potassium", "value": value},
                    headers=headers,
                )
            ).json()
            saved = (
                await client.post(
                    "/api/results/labs",
                    json=_body(patient, value=value, taken_at=f"2026-10-0{int(value)}T08:00:00+00:00"),
                    headers=headers,
                )
            ).json()
            assert preview["severity"] == saved["severity"]
            assert preview["reason"] == saved["classification_reason"]

    async def test_an_edited_range_changes_the_outcome(self, client, headers):
        default = (
            await client.post(
                "/api/results/labs/preview", json={"test_name": "potassium", "value": 5.2}, headers=headers
            )
        ).json()
        widened = (
            await client.post(
                "/api/results/labs/preview",
                json={"test_name": "potassium", "value": 5.2, "reference_low": 3.0, "reference_high": 6.0},
                headers=headers,
            )
        ).json()

        assert default["severity"] == "abnormal"
        assert widened["severity"] == "normal"

    @pytest.mark.parametrize("value", [-1, 62, 0.01])
    async def test_an_impossible_value_is_refused_with_a_reason(self, client, headers, value):
        res = await client.post(
            "/api/results/labs/preview", json={"test_name": "potassium", "value": value}, headers=headers
        )

        assert res.status_code == 422
        assert "potassium" in res.text or "not a possible" in res.text


class TestSaving:
    async def test_an_impossible_value_is_never_stored(self, client, headers, patient):
        res = await client.post("/api/results/labs", json=_body(patient, value=62), headers=headers)

        assert res.status_code == 422

    async def test_a_future_draw_is_refused(self, client, headers, patient):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        res = await client.post("/api/results/labs", json=_body(patient, taken_at=future), headers=headers)

        assert res.status_code == 422
        assert "future" in res.text

    async def test_a_draw_a_minute_ahead_is_tolerated_for_clock_drift(self, client, headers, patient):
        soon = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()

        res = await client.post("/api/results/labs", json=_body(patient, taken_at=soon), headers=headers)

        assert res.status_code == 201

    async def test_saving_twice_for_the_same_draw_says_it_existed(self, client, headers, patient):
        body = _body(patient, taken_at="2026-10-10T08:00:00+00:00")

        first = (await client.post("/api/results/labs", json=body, headers=headers)).json()
        second = (await client.post("/api/results/labs", json=body, headers=headers)).json()

        assert first["created"] is True
        assert second["created"] is False
        assert second["id"] == first["id"]

    async def test_it_is_audited(self, client, headers, patient, db_session):
        await client.post("/api/results/labs", json=_body(patient), headers=headers)

        rows = (
            (await db_session.execute(select(PhiAccessLog).where(PhiAccessLog.patient_id == patient.id)))
            .scalars()
            .all()
        )
        assert rows

    async def test_an_unknown_patient_is_404(self, client, headers, patient):
        res = await client.post("/api/results/labs", json=_body(patient, patient_id="NOPE"), headers=headers)

        assert res.status_code == 404


class TestSnapshotKeepsTheUnit:
    async def test_the_panel_says_what_the_number_is_in(self, db_session, patient):
        await svc.record_lab_result(
            db_session,
            patient_id=patient.id,
            test_name="potassium",
            value=3.4,
            unit="mEq/L",
            now=datetime(2026, 9, 6, 9, 0),
        )
        await db_session.flush()

        assert patient.lab_results["potassium"] == "3.4 mEq/L"

    async def test_the_risk_engine_still_reads_the_number(self, db_session, patient):
        from sephiroth.safety.risk import _first_number

        assert _first_number("3.4 mEq/L") == 3.4
