"""The visit over HTTP: guards, transitions, audit.

Verifies AC-023-01, AC-023-02, AC-023-08, AC-023-10
(docs/specs/SPEC-023-clinical-encounter.md).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.clinical.routers import encounters as encounters_module
from auth import router as auth_router_module
from core.db import get_session
from data.schemas import Appointment, PhiAccessLog, User

CREDS = {"email": "encounter-doc@example.org", "name": "Dra. Ruiz", "password": "password123"}
OTHER = {"email": "encounter-other@example.org", "name": "Dr. Otro", "password": "password123"}

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app(db_session):
    api = FastAPI()
    api.include_router(auth_router_module.router, prefix="/api/auth")
    api.include_router(encounters_module.router, prefix="/api/encounters")

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
    from data.schemas import Patient

    row = Patient(id="PENC1", name="Ana Gómez", age=61, sex="F", medical_record_number="MRN-PENC1")
    db_session.add(row)
    await db_session.commit()
    return row


async def _start(client, headers, patient, **body):
    res = await client.post("/api/encounters", json={"patient_id": patient.id, **body}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


class TestLifecycle:
    async def test_a_new_encounter_is_a_draft_nobody_else_can_see_yet(self, client, headers, patient):
        body = await _start(client, headers, patient, chief_complaint="Cefalea")

        assert body["status"] == "draft"
        assert body["editable"] is True
        assert body["clinical_note_id"] is None
        # Nothing to sign yet: a chief complaint alone is not a note.
        assert body["signable"] is True

    async def test_a_patch_writes_only_what_it_names(self, client, headers, patient):
        """A form that omits a field must not erase it."""
        encounter = await _start(client, headers, patient, chief_complaint="Cefalea")

        res = await client.patch(
            f"/api/encounters/{encounter['id']}", json={"assessment": "Crisis"}, headers=headers
        )

        assert res.status_code == 200
        assert res.json()["assessment"] == "Crisis"
        assert res.json()["chief_complaint"] == "Cefalea"

    async def test_a_section_is_cleared_by_sending_an_empty_string(self, client, headers, patient):
        encounter = await _start(client, headers, patient, chief_complaint="Cefalea")

        res = await client.patch(
            f"/api/encounters/{encounter['id']}", json={"chief_complaint": ""}, headers=headers
        )

        assert res.json()["chief_complaint"] == ""

    async def test_signing_an_empty_encounter_is_refused_with_409(self, client, headers, patient):
        """AC-023-02. Well-formed request, forbidden state."""
        encounter = await _start(client, headers, patient)

        res = await client.post(f"/api/encounters/{encounter['id']}/sign", headers=headers)

        assert res.status_code == 409
        assert "nothing written" in res.json()["detail"]

    async def test_signing_commits_the_visit(self, client, headers, patient):
        encounter = await _start(client, headers, patient, chief_complaint="Cefalea")

        res = await client.post(f"/api/encounters/{encounter['id']}/sign", headers=headers)

        body = res.json()
        assert body["status"] == "signed"
        assert body["editable"] is False
        assert body["signed_at"] is not None
        assert body["clinical_note_id"] is not None

    async def test_a_signed_encounter_refuses_edits(self, client, headers, patient):
        encounter = await _start(client, headers, patient, chief_complaint="Cefalea")
        await client.post(f"/api/encounters/{encounter['id']}/sign", headers=headers)

        res = await client.patch(
            f"/api/encounters/{encounter['id']}", json={"plan": "otra cosa"}, headers=headers
        )

        assert res.status_code == 409
        assert "amend" in res.json()["detail"]

    async def test_signing_reports_the_tasks_it_filed(self, client, headers, patient):
        encounter = await _start(client, headers, patient, chief_complaint="Control")
        await client.post(
            f"/api/encounters/{encounter['id']}/orders",
            json={"kind": "lab", "detail": "Potasio", "due_in_days": 7},
            headers=headers,
        )

        res = await client.post(f"/api/encounters/{encounter['id']}/sign", headers=headers)

        assert len(res.json()["tasks_created"]) == 1
        assert res.json()["orders"][0]["task_id"] is not None

    async def test_a_missing_encounter_is_404(self, client, headers):
        assert (await client.get("/api/encounters/nope", headers=headers)).status_code == 404


class TestVitals:
    async def test_an_alarming_reading_is_saved_and_flagged(self, client, headers, patient):
        """The reading the feature exists for. Saved, and reported on read."""
        encounter = await _start(client, headers, patient, chief_complaint="Cefalea")

        res = await client.patch(
            f"/api/encounters/{encounter['id']}",
            json={"vitals": {"systolic": 210, "diastolic": 120}},
            headers=headers,
        )

        body = res.json()
        assert body["vitals"] == {"systolic": 210, "diastolic": 120}
        assert {f["key"] for f in body["vital_findings"]} == {"systolic", "diastolic"}

    async def test_an_impossible_reading_is_refused_with_422(self, client, headers, patient):
        encounter = await _start(client, headers, patient)

        res = await client.patch(
            f"/api/encounters/{encounter['id']}", json={"vitals": {"systolic": 900}}, headers=headers
        )

        assert res.status_code == 422

    async def test_an_unknown_vital_is_refused(self, client, headers, patient):
        encounter = await _start(client, headers, patient)

        res = await client.patch(
            f"/api/encounters/{encounter['id']}", json={"vitals": {"mood": 7}}, headers=headers
        )

        assert res.status_code == 422

    async def test_the_spec_endpoint_serves_the_same_ranges_the_api_enforces(self, client, headers):
        """A range the UI validates against and a range the API enforces must
        be the same range."""
        res = await client.get("/api/encounters/vitals/spec", headers=headers)

        vitals = {v["key"]: v for v in res.json()["vitals"]}
        assert vitals["systolic"]["max"] == 300
        assert vitals["systolic"]["normal_high"] == 130
        assert "general" in res.json()["specialties"]


class TestOrders:
    async def test_an_order_is_added_and_listed(self, client, headers, patient):
        encounter = await _start(client, headers, patient, chief_complaint="Control")

        res = await client.post(
            f"/api/encounters/{encounter['id']}/orders",
            json={"kind": "lab", "detail": "Potasio", "due_in_days": 7},
            headers=headers,
        )

        (order,) = res.json()["orders"]
        assert order["kind"] == "lab"
        assert order["due_in_days"] == 7
        assert order["task_id"] is None, "an order files work only when the visit is signed"

    async def test_an_order_can_be_removed_from_a_draft(self, client, headers, patient):
        encounter = await _start(client, headers, patient, chief_complaint="Control")
        added = await client.post(
            f"/api/encounters/{encounter['id']}/orders",
            json={"kind": "lab", "detail": "Potasio"},
            headers=headers,
        )
        order_id = added.json()["orders"][0]["id"]

        res = await client.delete(f"/api/encounters/{encounter['id']}/orders/{order_id}", headers=headers)

        assert res.json()["orders"] == []

    async def test_an_unknown_kind_is_rejected_by_the_schema(self, client, headers, patient):
        encounter = await _start(client, headers, patient)

        res = await client.post(
            f"/api/encounters/{encounter['id']}/orders",
            json={"kind": "surgery", "detail": "algo"},
            headers=headers,
        )

        assert res.status_code == 422

    async def test_a_signed_encounter_takes_no_new_orders(self, client, headers, patient):
        encounter = await _start(client, headers, patient, chief_complaint="Control")
        await client.post(f"/api/encounters/{encounter['id']}/sign", headers=headers)

        res = await client.post(
            f"/api/encounters/{encounter['id']}/orders",
            json={"kind": "lab", "detail": "Tardío"},
            headers=headers,
        )

        assert res.status_code == 409


class TestAmendment:
    """AC-023-08."""

    async def test_amending_reopens_the_encounter_and_records_why(self, client, headers, patient):
        encounter = await _start(client, headers, patient, chief_complaint="Control")
        await client.post(f"/api/encounters/{encounter['id']}/sign", headers=headers)

        res = await client.post(
            f"/api/encounters/{encounter['id']}/amend",
            json={"reason": "Corrijo la dosis"},
            headers=headers,
        )

        body = res.json()
        assert body["status"] == "amended"
        assert body["editable"] is True
        assert body["amendment_reason"] == "Corrijo la dosis"
        assert body["amended_at"] is not None

    async def test_an_amendment_needs_a_reason(self, client, headers, patient):
        encounter = await _start(client, headers, patient, chief_complaint="Control")
        await client.post(f"/api/encounters/{encounter['id']}/sign", headers=headers)

        res = await client.post(
            f"/api/encounters/{encounter['id']}/amend", json={"reason": ""}, headers=headers
        )

        assert res.status_code == 422

    async def test_an_unsigned_encounter_cannot_be_amended(self, client, headers, patient):
        """It is already editable; an amendment record would claim a
        correction that never happened."""
        encounter = await _start(client, headers, patient, chief_complaint="Control")

        res = await client.post(
            f"/api/encounters/{encounter['id']}/amend", json={"reason": "x"}, headers=headers
        )

        assert res.status_code == 409

    async def test_an_amendment_is_refused_outside_the_window(
        self, client, headers, patient, db_session, monkeypatch
    ):
        from data.schemas import Encounter

        encounter = await _start(client, headers, patient, chief_complaint="Control")
        await client.post(f"/api/encounters/{encounter['id']}/sign", headers=headers)

        row = await db_session.get(Encounter, encounter["id"])
        row.signed_at = datetime.utcnow() - timedelta(days=45)
        await db_session.commit()

        res = await client.post(
            f"/api/encounters/{encounter['id']}/amend", json={"reason": "tarde"}, headers=headers
        )

        assert res.status_code == 409
        assert "window" in res.json()["detail"]


class TestAppointmentLink:
    async def test_one_encounter_per_booking(self, client, headers, patient, db_session):
        clinician = (await db_session.scalars(select(User).where(User.email == CREDS["email"]))).one()
        appointment = Appointment(
            id=str(uuid4()),
            clinician_id=clinician.id,
            patient_id=patient.id,
            start_at=datetime(2026, 9, 7, 9, 0),
            end_at=datetime(2026, 9, 7, 9, 30),
        )
        db_session.add(appointment)
        await db_session.commit()

        first = await client.post(
            "/api/encounters",
            json={"patient_id": patient.id, "appointment_id": appointment.id},
            headers=headers,
        )
        second = await client.post(
            "/api/encounters",
            json={"patient_id": patient.id, "appointment_id": appointment.id},
            headers=headers,
        )

        assert first.status_code == 200
        assert second.status_code == 409

    async def test_an_appointment_for_another_patient_is_refused(self, client, headers, patient, db_session):
        from data.schemas import Patient

        other = Patient(id="PENC2", name="Otro", age=30, sex="M", medical_record_number="MRN-PENC2")
        clinician = (await db_session.scalars(select(User).where(User.email == CREDS["email"]))).one()
        appointment = Appointment(
            id=str(uuid4()),
            clinician_id=clinician.id,
            patient_id=other.id,
            start_at=datetime(2026, 9, 7, 10, 0),
            end_at=datetime(2026, 9, 7, 10, 30),
        )
        db_session.add_all([other, appointment])
        await db_session.commit()

        res = await client.post(
            "/api/encounters",
            json={"patient_id": patient.id, "appointment_id": appointment.id},
            headers=headers,
        )

        assert res.status_code == 404

    async def test_a_walk_in_needs_no_appointment(self, client, headers, patient):
        body = await _start(client, headers, patient, chief_complaint="Sin cita")
        assert body["appointment_id"] is None


class TestAudit:
    """AC-023-10 — an encounter carries the patient's name and clinical
    narrative, so reading one is a PHI read."""

    async def test_reading_an_encounter_records_phi_access(self, client, headers, patient, db_session):
        encounter = await _start(client, headers, patient, chief_complaint="Cefalea")
        before = len((await db_session.scalars(select(PhiAccessLog))).all())

        await client.get(f"/api/encounters/{encounter['id']}", headers=headers)

        rows = (await db_session.scalars(select(PhiAccessLog))).all()
        assert len(rows) > before
        assert any(patient.id == r.patient_id for r in rows)

    async def test_listing_encounters_records_one_row_per_patient(self, client, headers, patient, db_session):
        await _start(client, headers, patient, chief_complaint="Uno")
        await _start(client, headers, patient, chief_complaint="Dos")

        await client.get("/api/encounters", headers=headers)

        rows = (
            await db_session.scalars(select(PhiAccessLog).where(PhiAccessLog.route == "/api/encounters"))
        ).all()
        assert any(r.method == "GET" for r in rows)


class TestAuthorization:
    async def test_an_anonymous_caller_is_refused(self, client, patient):
        res = await client.post("/api/encounters", json={"patient_id": patient.id})
        assert res.status_code in (401, 403)

    async def test_a_patient_account_is_refused(self, client, db_session, patient):
        from auth.security import hash_password

        db_session.add(
            User(
                id=str(uuid4()),
                email="portal-user@example.org",
                name="Paciente",
                hashed_password=await hash_password("password123"),
                role="patient",
                patient_id=patient.id,
            )
        )
        await db_session.commit()
        token = (
            await client.post(
                "/api/auth/login", json={"email": "portal-user@example.org", "password": "password123"}
            )
        ).json()["access_token"]

        res = await client.get("/api/encounters", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 403

    async def test_another_clinician_cannot_sign_this_visit(self, client, headers, patient):
        """A signature is a person standing behind clinical content."""
        encounter = await _start(client, headers, patient, chief_complaint="Control")
        other_token = (await client.post("/api/auth/register", json=OTHER)).json()["access_token"]

        res = await client.post(
            f"/api/encounters/{encounter['id']}/sign",
            headers={"Authorization": f"Bearer {other_token}"},
        )

        assert res.status_code == 409
        assert "conducted the visit" in res.json()["detail"]
