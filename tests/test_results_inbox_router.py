"""The results inbox over HTTP.

Verifies AC-024-10 and the HTTP surface of the loop
(docs/specs/SPEC-024-results-loop.md).
"""

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.clinical.routers import result_reviews as reviews_module
from auth import router as auth_router_module
from core.db import get_session
from data.schemas import Patient, PhiAccessLog, TimelineEvent, User

CREDS = {"email": "results-doc@example.org", "name": "Dra. Ruiz", "password": "password123"}

pytestmark = pytest.mark.asyncio


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
    row = Patient(id="PRES1", name="Ana Gómez", age=61, sex="F", medical_record_number="MRN-PRES1")
    db_session.add(row)
    await db_session.commit()
    return row


async def _lab(client, headers, patient, **body):
    payload = {"patient_id": patient.id, "test_name": "potassium", "value": 6.2, "unit": "mEq/L"}
    payload.update(body)
    res = await client.post("/api/results/labs", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


class TestIntake:
    async def test_a_lab_is_recorded_and_classified(self, client, headers, patient):
        body = await _lab(client, headers, patient)

        assert body["created"] is True
        assert body["status"] == "received"
        assert body["severity"] == "critical"
        assert body["result"]["test_name"] == "potassium"

    async def test_recording_it_again_reports_that_nothing_was_created(self, client, headers, patient):
        taken = "2026-09-06T09:00:00+00:00"
        first = await _lab(client, headers, patient, taken_at=taken)
        second = await _lab(client, headers, patient, taken_at=taken)

        assert second["created"] is False
        assert second["id"] == first["id"]

    async def test_an_unknown_patient_is_404(self, client, headers):
        res = await client.post(
            "/api/results/labs",
            json={"patient_id": "nope", "test_name": "potassium", "value": 4.1},
            headers=headers,
        )

        assert res.status_code == 404

    async def test_an_imaging_study_is_recorded(self, client, headers, patient):
        res = await client.post(
            "/api/results/imaging",
            json={
                "patient_id": patient.id,
                "modality": "TAC",
                "body_part": "cráneo",
                "severity": "review",
                "finding_summary": "Nódulo de 8mm",
            },
            headers=headers,
        )

        body = res.json()
        assert res.status_code == 201
        assert body["severity"] == "abnormal"
        assert body["result"]["modality"] == "TAC"

    async def test_an_unknown_study_severity_is_rejected_by_the_schema(self, client, headers, patient):
        res = await client.post(
            "/api/results/imaging",
            json={
                "patient_id": patient.id,
                "modality": "TAC",
                "body_part": "cráneo",
                "severity": "terrible",
            },
            headers=headers,
        )

        assert res.status_code == 422


class TestInbox:
    async def test_it_lists_what_is_waiting(self, client, headers, patient):
        await _lab(client, headers, patient, taken_at="2026-09-06T09:00:00+00:00")
        await _lab(
            client, headers, patient, test_name="creatinine", value=2.4, taken_at="2026-09-06T10:00:00+00:00"
        )

        res = await client.get("/api/results/inbox", headers=headers)

        assert [item["severity"] for item in res.json()["items"]] == ["critical", "abnormal"]

    async def test_a_normal_result_is_still_in_the_inbox(self, client, headers, patient):
        """It made no task, because it is not work. It is still a result
        somebody has not signed off on."""
        await _lab(client, headers, patient, value=4.1)

        res = await client.get("/api/results/inbox", headers=headers)

        assert [item["severity"] for item in res.json()["items"]] == ["normal"]

    async def test_it_filters_by_severity(self, client, headers, patient):
        await _lab(client, headers, patient, taken_at="2026-09-06T09:00:00+00:00")
        await _lab(
            client, headers, patient, test_name="creatinine", value=2.4, taken_at="2026-09-06T10:00:00+00:00"
        )

        res = await client.get("/api/results/inbox?severity=critical", headers=headers)

        assert len(res.json()["items"]) == 1

    async def test_it_says_what_a_row_can_do_before_offering_a_button(self, client, headers, patient):
        """So a refusal is never a surprise 409."""
        review = await _lab(client, headers, patient)

        assert review["closable"] is False
        assert review["needs_communication"] is False


class TestTheLoopOverHttp:
    async def test_review_records_the_decision(self, client, headers, patient):
        review = await _lab(client, headers, patient)

        res = await client.post(
            f"/api/results/reviews/{review['id']}/review",
            json={"disposition": "action_taken", "note": "Suspendo el IECA"},
            headers=headers,
        )

        body = res.json()
        assert body["status"] == "reviewed"
        assert body["note"] == "Suspendo el IECA"
        assert body["closable"] is True

    async def test_a_missing_note_is_refused_with_409(self, client, headers, patient):
        review = await _lab(client, headers, patient)

        res = await client.post(
            f"/api/results/reviews/{review['id']}/review",
            json={"disposition": "abnormal_expected", "note": ""},
            headers=headers,
        )

        assert res.status_code == 409

    async def test_closing_a_result_that_needs_contact_is_refused(self, client, headers, patient):
        review = await _lab(client, headers, patient)
        await client.post(
            f"/api/results/reviews/{review['id']}/review",
            json={"disposition": "needs_patient_contact", "note": "Avisar"},
            headers=headers,
        )

        res = await client.post(f"/api/results/reviews/{review['id']}/close", headers=headers)

        assert res.status_code == 409
        assert "communicate it before closing" in res.json()["detail"]

    async def test_the_row_says_it_needs_communicating(self, client, headers, patient):
        review = await _lab(client, headers, patient)

        res = await client.post(
            f"/api/results/reviews/{review['id']}/review",
            json={"disposition": "needs_patient_contact", "note": "Avisar"},
            headers=headers,
        )

        assert res.json()["needs_communication"] is True
        assert res.json()["closable"] is False

    async def test_communicating_then_closing_completes_the_loop(self, client, headers, patient, db_session):
        event = TimelineEvent(
            patient_id=patient.id, date=datetime(2026, 9, 6).date(), type="lab", title="Potasio"
        )
        db_session.add(event)
        await db_session.commit()

        review = await _lab(client, headers, patient)
        await client.post(
            f"/api/results/reviews/{review['id']}/review",
            json={"disposition": "needs_patient_contact", "note": "Avisar"},
            headers=headers,
        )
        communicated = await client.post(
            f"/api/results/reviews/{review['id']}/communicate",
            json={"message": "Su potasio está alto.", "timeline_event_id": event.id},
            headers=headers,
        )
        closed = await client.post(f"/api/results/reviews/{review['id']}/close", headers=headers)

        assert communicated.json()["status"] == "communicated"
        assert communicated.json()["share_id"] is not None
        assert closed.json()["status"] == "closed"

    async def test_a_timeline_entry_belonging_to_someone_else_is_refused(
        self, client, headers, patient, db_session
    ):
        """It would show one patient another patient's result."""
        other = Patient(id="PRES2", name="Otro", age=40, sex="M", medical_record_number="MRN-PRES2")
        db_session.add(other)
        await db_session.flush()
        event = TimelineEvent(
            patient_id=other.id, date=datetime(2026, 9, 6).date(), type="lab", title="Ajeno"
        )
        db_session.add(event)
        await db_session.commit()

        review = await _lab(client, headers, patient)
        await client.post(
            f"/api/results/reviews/{review['id']}/review",
            json={"disposition": "needs_patient_contact", "note": "Avisar"},
            headers=headers,
        )

        res = await client.post(
            f"/api/results/reviews/{review['id']}/communicate",
            json={"message": "x", "timeline_event_id": event.id},
            headers=headers,
        )

        assert res.status_code == 404

    async def test_reopening_undoes_a_close(self, client, headers, patient):
        review = await _lab(client, headers, patient)
        await client.post(
            f"/api/results/reviews/{review['id']}/review",
            json={"disposition": "action_taken", "note": "Hecho"},
            headers=headers,
        )
        await client.post(f"/api/results/reviews/{review['id']}/close", headers=headers)

        res = await client.post(f"/api/results/reviews/{review['id']}/reopen", headers=headers)

        assert res.json()["status"] == "reviewed"
        assert res.json()["closed_at"] is None

    async def test_a_missing_review_is_404(self, client, headers):
        res = await client.post("/api/results/reviews/nope/close", headers=headers)

        assert res.status_code == 404


class TestAudit:
    """AC-024-10 — a result carries a patient's clinical values, so listing
    them is a PHI read."""

    async def test_reading_the_inbox_records_access(self, client, headers, patient, db_session):
        await _lab(client, headers, patient)

        await client.get("/api/results/inbox", headers=headers)

        rows = (
            await db_session.scalars(select(PhiAccessLog).where(PhiAccessLog.route == "/api/results/inbox"))
        ).all()
        assert rows and all(row.patient_id == patient.id for row in rows)

    async def test_reading_one_review_records_access(self, client, headers, patient, db_session):
        review = await _lab(client, headers, patient)

        await client.get(f"/api/results/reviews/{review['id']}", headers=headers)

        rows = (
            await db_session.scalars(
                select(PhiAccessLog).where(PhiAccessLog.route == f"/api/results/reviews/{review['id']}")
            )
        ).all()
        assert len(rows) == 1


class TestAuthorization:
    async def test_an_anonymous_caller_is_refused(self, client, patient):
        res = await client.get("/api/results/inbox")

        assert res.status_code in (401, 403)

    async def test_a_patient_account_is_refused(self, client, db_session, patient):
        from auth.security import hash_password

        db_session.add(
            User(
                id=str(uuid4()),
                email="results-portal@example.org",
                name="Paciente",
                hashed_password=await hash_password("password123"),
                role="patient",
                patient_id=patient.id,
            )
        )
        await db_session.commit()
        token = (
            await client.post(
                "/api/auth/login",
                json={"email": "results-portal@example.org", "password": "password123"},
            )
        ).json()["access_token"]

        res = await client.get("/api/results/inbox", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 403
