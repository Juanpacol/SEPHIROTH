"""The brief a clinician reads in the thirty seconds before a patient walks in.

Assembled on read from rows that already exist. The test that matters most is
the one asserting it writes nothing: a cached brief is wrong the moment a lab
comes back, and the entire value of this one is that it is true when opened.

Verifies AC-023-09 (docs/specs/SPEC-023-clinical-encounter.md).
"""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from api.services import encounter_service as enc
from api.services import task_service
from api.services.pre_visit import build_pre_visit_brief
from data.schemas import Alert, Appointment, ImagingStudy, LabResult, Patient, User

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 9, 0)


async def _clinician(session):
    user = User(
        id=str(uuid4()),
        email=f"{uuid4().hex[:8]}@example.org",
        name="Dra. Ruiz",
        hashed_password="x",
        role="clinician",
    )
    session.add(user)
    await session.flush()
    return user


async def _patient(session, **fields):
    patient = Patient(
        id=f"P{uuid4().hex[:6]}",
        name="Ana Gómez",
        age=61,
        sex="F",
        medical_record_number=f"MRN-{uuid4().hex[:6]}",
        medications=fields.pop("medications", ["Losartán 50mg"]),
        allergies=fields.pop("allergies", ["penicilina"]),
        conditions=fields.pop("conditions", ["Hipertensión"]),
        lab_results=fields.pop("lab_results", {}),
        **fields,
    )
    session.add(patient)
    await session.flush()
    return patient


class TestWhatItGathers:
    async def test_it_names_the_patient_and_their_standing_facts(self, db_session):
        patient = await _patient(db_session)

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert brief["patient"]["name"] == "Ana Gómez"
        assert brief["medications"] == ["Losartán 50mg"]
        assert brief["allergies"] == ["penicilina"]
        assert brief["conditions"] == ["Hipertensión"]

    async def test_it_leads_with_why_they_are_here(self, db_session):
        patient = await _patient(db_session)
        clinician = await _clinician(db_session)
        db_session.add(
            Appointment(
                id=str(uuid4()),
                clinician_id=clinician.id,
                patient_id=patient.id,
                start_at=NOW + timedelta(hours=1),
                end_at=NOW + timedelta(hours=1, minutes=30),
                reason="Control de presión",
            )
        )
        await db_session.flush()

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert brief["reason"] == "Control de presión"
        assert brief["next_appointment"]["confirmed"] is False

    async def test_a_past_appointment_is_not_the_next_one(self, db_session):
        patient = await _patient(db_session)
        clinician = await _clinician(db_session)
        db_session.add(
            Appointment(
                id=str(uuid4()),
                clinician_id=clinician.id,
                patient_id=patient.id,
                start_at=NOW - timedelta(days=30),
                end_at=NOW - timedelta(days=30) + timedelta(minutes=30),
                reason="Vieja",
            )
        )
        await db_session.flush()

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert brief["next_appointment"] is None
        assert brief["reason"] == ""

    async def test_it_shows_the_last_visits_but_not_an_unfinished_one(self, db_session):
        """A draft is somebody's unfinished thought, not a record of a visit.
        Showing it as history would present it as something it is not."""
        patient = await _patient(db_session)
        clinician = await _clinician(db_session)

        signed = await enc.create_encounter(
            db_session, patient_id=patient.id, clinician=clinician, chief_complaint="Cefalea"
        )
        await db_session.flush()
        await enc.sign_encounter(db_session, signed, signer=clinician, now=NOW - timedelta(days=7))
        await enc.create_encounter(
            db_session, patient_id=patient.id, clinician=clinician, chief_complaint="Sin terminar"
        )
        await db_session.flush()

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert [e["chief_complaint"] for e in brief["recent_encounters"]] == ["Cefalea"]

    async def test_it_shows_what_is_still_open(self, db_session):
        patient = await _patient(db_session)
        await task_service.create_task(
            db_session,
            source_type="alert",
            source_id="A1",
            category="lab",
            severity="high",
            title="Revisar potasio",
            dedupe_key=f"alert:{uuid4().hex}",
            patient_id=patient.id,
            now=NOW - timedelta(days=3),
        )
        db_session.add(
            Alert(
                id=str(uuid4()),
                patient_id=patient.id,
                category="lab",
                severity="high",
                title="Potasio alto",
                source="K+ > 5.5 mEq/L",
            )
        )
        await db_session.flush()

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert [t["title"] for t in brief["open_tasks"]] == ["Revisar potasio"]
        assert [a["title"] for a in brief["alerts"]] == ["Potasio alto"]

    async def test_an_overdue_task_says_so(self, db_session):
        patient = await _patient(db_session)
        await task_service.create_task(
            db_session,
            source_type="alert",
            source_id="A2",
            category="lab",
            severity="critical",
            title="Vencida",
            dedupe_key=f"alert:{uuid4().hex}",
            patient_id=patient.id,
            now=NOW - timedelta(days=5),
        )
        await db_session.flush()

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert brief["open_tasks"][0]["overdue"] is True

    async def test_it_shows_results_that_came_back_since_the_last_visit(self, db_session):
        patient = await _patient(db_session)
        db_session.add_all(
            [
                LabResult(
                    patient_id=patient.id,
                    test_name="Potasio",
                    value="6.2",
                    unit="mEq/L",
                    taken_at=NOW - timedelta(days=2),
                    is_critical=True,
                ),
                ImagingStudy(
                    id=str(uuid4()),
                    patient_id=patient.id,
                    modality="TAC",
                    body_part="cráneo",
                    study_date=date(2026, 9, 1),
                    severity="review",
                ),
            ]
        )
        await db_session.flush()

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        by_name = {r["name"]: r for r in brief["recent_results"]}
        assert by_name["Potasio"]["critical"] is True
        assert by_name["TAC cráneo"]["abnormal"] is True

    async def test_stale_results_are_left_out(self, db_session):
        """Beyond the lookback the brief stops being something read in thirty
        seconds."""
        patient = await _patient(db_session)
        db_session.add(
            LabResult(
                patient_id=patient.id,
                test_name="Antiguo",
                value="1",
                unit="",
                taken_at=NOW - timedelta(days=400),
            )
        )
        await db_session.flush()

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert brief["recent_results"] == []

    async def test_risk_flags_come_from_the_same_rules_the_chart_uses(self, db_session):
        """The brief and the patient page cannot disagree about whether
        something is a risk."""
        patient = await _patient(db_session, lab_results={"potassium": "6.2"})

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert any(f["rule_key"] == "lab.potassium.high" for f in brief["risk_flags"])

    async def test_a_patient_with_no_history_yields_an_empty_brief_not_an_error(self, db_session):
        patient = await _patient(db_session, medications=[], allergies=[], conditions=[], lab_results={})

        brief = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert brief["recent_encounters"] == []
        assert brief["open_tasks"] == []
        assert brief["recent_results"] == []
        assert brief["risk_flags"] == []


class TestItWritesNothing:
    """AC-023-09's second half."""

    async def _counts(self, session):
        from data.schemas import Encounter, PhiAccessLog, Task

        return {
            model.__name__: await session.scalar(select(func.count()).select_from(model))
            for model in (Encounter, Task, PhiAccessLog, Alert)
        }

    async def test_building_the_brief_creates_no_rows(self, db_session):
        patient = await _patient(db_session, lab_results={"potassium": "6.2"})
        await db_session.flush()
        before = await self._counts(db_session)

        await build_pre_visit_brief(db_session, patient, now=NOW)
        await build_pre_visit_brief(db_session, patient, now=NOW)
        await db_session.flush()

        assert await self._counts(db_session) == before

    async def test_two_reads_of_an_unchanged_patient_agree(self, db_session):
        patient = await _patient(db_session)

        first = await build_pre_visit_brief(db_session, patient, now=NOW)
        second = await build_pre_visit_brief(db_session, patient, now=NOW)

        assert first == second
