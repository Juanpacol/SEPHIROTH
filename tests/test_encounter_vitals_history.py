"""A patient's vitals history, as the encounter form uses it.

Two things, deliberately kept apart:

* `GET /api/encounters/last-vitals` -- the latest recorded value of *every* vital,
  as a read-only reference shown next to each field. Never stored by the client.
* `create_encounter` -- copies only weight and height (`CARRY_FORWARD_VITALS`).
  Everything else is a measurement of the moment and must be taken again.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.routers import encounters as encounters_module
from api.services import encounter_service as svc
from auth import router as auth_router_module
from core.db import get_session
from data.schemas import Encounter, Patient, PhiAccessLog, User

CREDS = {"email": "vitals-history@example.org", "name": "Dra. Vidal", "password": "password123"}
BASE = datetime(2026, 1, 1, 9, 0, 0)

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
async def clinician(headers, db_session):
    return await db_session.scalar(select(User).where(User.email == CREDS["email"]))


async def _patient(db_session, patient_id="PVH1"):
    row = Patient(id=patient_id, name="Ana Gómez", age=61, sex="F", medical_record_number=f"MRN-{patient_id}")
    db_session.add(row)
    await db_session.commit()
    return row


@pytest.fixture
async def patient(db_session):
    return await _patient(db_session)


async def _visit(db_session, clinician, patient, *, days_ago, vitals, status="signed"):
    """An encounter at a controlled date. Signed/amended rows need a signer."""
    started = BASE + timedelta(days=100 - days_ago)
    encounter = Encounter(
        id=str(uuid4()),
        patient_id=patient.id,
        clinician_id=clinician.id,
        status=status,
        vitals=vitals,
        started_at=started,
        created_at=started,
        updated_at=started,
        signed_at=None if status == "draft" else started,
        signed_by=None if status == "draft" else clinician.id,
        amended_at=started if status == "amended" else None,
        amendment_reason="corrección" if status == "amended" else "",
    )
    db_session.add(encounter)
    await db_session.commit()
    return encounter


async def _last(client, headers, patient, **params):
    res = await client.get(
        "/api/encounters/last-vitals", params={"patient_id": patient.id, **params}, headers=headers
    )
    assert res.status_code == 200, res.text
    return res.json()["readings"]


class TestEachVitalComesFromItsOwnLatestVisit:
    async def test_weight_and_height_can_come_from_different_visits(
        self, client, headers, clinician, patient, db_session
    ):
        await _visit(db_session, clinician, patient, days_ago=400, vitals={"height": 170, "weight": 72})
        await _visit(db_session, clinician, patient, days_ago=10, vitals={"weight": 70})

        readings = await _last(client, headers, patient)

        assert readings["weight"]["value"] == 70
        assert readings["height"]["value"] == 170
        # Different visits, so different dates.
        assert readings["weight"]["at"] != readings["height"]["at"]

    async def test_a_reading_carries_its_visit_date_and_id(
        self, client, headers, clinician, patient, db_session
    ):
        visit = await _visit(db_session, clinician, patient, days_ago=5, vitals={"heart_rate": 64})

        reading = (await _last(client, headers, patient))["heart_rate"]

        assert reading == {
            "value": 64.0,
            "at": visit.started_at.isoformat(),
            "encounter_id": visit.id,
        }

    async def test_the_whole_history_counts_not_just_the_latest_ten(
        self, client, headers, clinician, patient, db_session
    ):
        await _visit(db_session, clinician, patient, days_ago=900, vitals={"weight": 80})
        for i in range(12):
            await _visit(db_session, clinician, patient, days_ago=100 - i, vitals={"heart_rate": 70})

        readings = await _last(client, headers, patient)

        assert readings["weight"]["value"] == 80


class TestBloodPressureIsOneReading:
    async def test_it_comes_from_a_single_visit(self, client, headers, clinician, patient, db_session):
        older = await _visit(
            db_session, clinician, patient, days_ago=60, vitals={"systolic": 130, "diastolic": 85}
        )
        # The newest visit has only a systolic: a lone half is not a reading.
        await _visit(db_session, clinician, patient, days_ago=5, vitals={"systolic": 150})

        readings = await _last(client, headers, patient)

        assert (readings["systolic"]["value"], readings["diastolic"]["value"]) == (130, 85)
        assert readings["systolic"]["encounter_id"] == readings["diastolic"]["encounter_id"] == older.id

    async def test_a_lone_half_with_no_pair_anywhere_is_not_reported(
        self, client, headers, clinician, patient, db_session
    ):
        await _visit(db_session, clinician, patient, days_ago=5, vitals={"systolic": 150})
        await _visit(db_session, clinician, patient, days_ago=50, vitals={"diastolic": 90})

        readings = await _last(client, headers, patient)

        assert "systolic" not in readings and "diastolic" not in readings


class TestWhichVisitsAndValuesCount:
    async def test_drafts_are_ignored(self, client, headers, clinician, patient, db_session):
        await _visit(db_session, clinician, patient, days_ago=2, vitals={"weight": 99}, status="draft")
        await _visit(db_session, clinician, patient, days_ago=30, vitals={"weight": 70})

        assert (await _last(client, headers, patient))["weight"]["value"] == 70

    async def test_amended_visits_count(self, client, headers, clinician, patient, db_session):
        await _visit(db_session, clinician, patient, days_ago=3, vitals={"weight": 71}, status="amended")

        assert (await _last(client, headers, patient))["weight"]["value"] == 71

    async def test_the_encounter_being_edited_is_never_its_own_source(
        self, client, headers, clinician, patient, db_session
    ):
        older = await _visit(db_session, clinician, patient, days_ago=90, vitals={"weight": 70})
        being_amended = await _visit(
            db_session, clinician, patient, days_ago=3, vitals={"weight": 99}, status="amended"
        )

        readings = await _last(client, headers, patient, exclude_encounter_id=being_amended.id)

        assert readings["weight"]["value"] == 70
        assert readings["weight"]["encounter_id"] == older.id

    async def test_a_value_no_body_produces_is_skipped_in_favour_of_an_earlier_one(
        self, client, headers, clinician, patient, db_session
    ):
        await _visit(db_session, clinician, patient, days_ago=40, vitals={"weight": 70})
        await _visit(db_session, clinician, patient, days_ago=5, vitals={"weight": 0})

        assert (await _last(client, headers, patient))["weight"]["value"] == 70

    async def test_a_pain_score_of_zero_is_a_real_answer(
        self, client, headers, clinician, patient, db_session
    ):
        await _visit(db_session, clinician, patient, days_ago=5, vitals={"pain_score": 0})

        assert (await _last(client, headers, patient))["pain_score"]["value"] == 0

    async def test_another_patients_history_is_not_used(
        self, client, headers, clinician, patient, db_session
    ):
        other = await _patient(db_session, "PVH2")
        await _visit(db_session, clinician, other, days_ago=5, vitals={"weight": 55})

        assert await _last(client, headers, patient) == {}

    async def test_no_history_is_an_empty_answer_not_an_error(self, client, headers, patient):
        assert await _last(client, headers, patient) == {}


class TestTheEndpoint:
    async def test_an_unknown_patient_is_a_404(self, client, headers):
        res = await client.get("/api/encounters/last-vitals", params={"patient_id": "NOPE"}, headers=headers)

        assert res.status_code == 404

    async def test_a_patient_id_is_required(self, client, headers):
        res = await client.get("/api/encounters/last-vitals", headers=headers)

        assert res.status_code == 422

    async def test_an_anonymous_caller_is_refused(self, client, patient):
        res = await client.get("/api/encounters/last-vitals", params={"patient_id": patient.id})

        assert res.status_code in (401, 403)

    async def test_reading_the_history_is_one_phi_access(
        self, client, headers, clinician, patient, db_session
    ):
        for days in (5, 50, 90):
            await _visit(db_session, clinician, patient, days_ago=days, vitals={"weight": 70})

        await client.get("/api/encounters/last-vitals", params={"patient_id": patient.id}, headers=headers)

        rows = (
            await db_session.scalars(
                select(PhiAccessLog).where(PhiAccessLog.route == "/api/encounters/last-vitals")
            )
        ).all()
        # One row per call, not one per visit read.
        assert len(rows) == 1
        assert rows[0].patient_id == patient.id


class TestANewEncounterCarriesOnlyWeightAndHeight:
    async def _start(self, client, headers, patient, **body):
        res = await client.post("/api/encounters", json={"patient_id": patient.id, **body}, headers=headers)
        assert res.status_code == 200, res.text
        return res.json()

    async def test_weight_and_height_arrive_filled_each_from_its_latest_visit(
        self, client, headers, clinician, patient, db_session
    ):
        await _visit(db_session, clinician, patient, days_ago=400, vitals={"height": 170, "weight": 72})
        await _visit(db_session, clinician, patient, days_ago=10, vitals={"weight": 70})

        body = await self._start(client, headers, patient, chief_complaint="Control")

        assert body["vitals"] == {"weight": 70, "height": 170}

    async def test_a_measurement_of_the_moment_is_never_copied(
        self, client, headers, clinician, patient, db_session
    ):
        await _visit(
            db_session,
            clinician,
            patient,
            days_ago=10,
            vitals={
                "weight": 70,
                "systolic": 120,
                "diastolic": 80,
                "heart_rate": 70,
                "respiratory_rate": 16,
                "temperature": 36.6,
                "oxygen_saturation": 98,
                "glucose": 95,
                "pain_score": 2,
            },
        )

        body = await self._start(client, headers, patient)

        assert body["vitals"] == {"weight": 70}
        assert body["vital_findings"] == []

    async def test_no_history_means_no_vitals(self, client, headers, patient):
        body = await self._start(client, headers, patient)

        assert body["vitals"] == {}

    async def test_copied_vitals_do_not_make_an_empty_visit_signable(
        self, client, headers, clinician, patient, db_session
    ):
        await _visit(db_session, clinician, patient, days_ago=10, vitals={"weight": 70, "height": 170})

        body = await self._start(client, headers, patient)

        assert body["vitals"] == {"weight": 70, "height": 170}
        assert body["signable"] is False

    async def test_the_carried_values_can_be_edited_or_cleared(
        self, client, headers, clinician, patient, db_session
    ):
        await _visit(db_session, clinician, patient, days_ago=10, vitals={"weight": 70, "height": 170})
        body = await self._start(client, headers, patient, chief_complaint="Control")

        res = await client.patch(
            f"/api/encounters/{body['id']}", json={"vitals": {"weight": 68}}, headers=headers
        )

        assert res.json()["vitals"] == {"weight": 68}

    async def test_the_service_default_still_works_without_a_history(self, db_session, clinician, patient):
        encounter = await svc.create_encounter(db_session, patient_id=patient.id, clinician=clinician)

        assert encounter.vitals == {}
        assert svc.CARRY_FORWARD_VITALS == ("weight", "height")
