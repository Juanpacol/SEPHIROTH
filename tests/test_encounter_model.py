"""What the database refuses, independently of the service that usually guards it.

A rule that lives only in Python is a comment: it holds until somebody writes a
row from a script, a migration, or a second code path. These constraints are
the ones worth having in the schema — a signed record nobody stands behind, an
amendment with no reason, an order of a kind nothing knows how to file.

Verifies AC-023-01's persistence half
(docs/specs/SPEC-023-clinical-encounter.md).
"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from data.schemas import Encounter, EncounterOrder, Patient, User

pytestmark = pytest.mark.asyncio


async def _people(session):
    clinician = User(
        id=str(uuid4()),
        email=f"{uuid4().hex[:8]}@example.org",
        name="Dra. Ruiz",
        hashed_password="x",
        role="clinician",
    )
    patient = Patient(
        id=f"P{uuid4().hex[:6]}",
        name="Ana",
        age=61,
        sex="F",
        medical_record_number=f"MRN-{uuid4().hex[:6]}",
    )
    session.add_all([clinician, patient])
    await session.flush()
    return clinician, patient


def _row(clinician, patient, **fields):
    return Encounter(
        id=str(uuid4()),
        patient_id=patient.id,
        clinician_id=clinician.id,
        started_at=datetime(2026, 9, 6, 9, 0),
        **fields,
    )


class TestConstraints:
    async def test_a_signed_encounter_cannot_lack_a_signer(self, db_session):
        """The one that matters: a clinical record nobody stands behind."""
        clinician, patient = await _people(db_session)
        db_session.add(_row(clinician, patient, status="signed"))

        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_a_signed_encounter_with_a_signer_is_accepted(self, db_session):
        clinician, patient = await _people(db_session)
        db_session.add(
            _row(
                clinician,
                patient,
                status="signed",
                signed_at=datetime(2026, 9, 6, 10, 0),
                signed_by=clinician.id,
            )
        )

        await db_session.flush()

        assert (await db_session.scalars(select(Encounter))).one().status == "signed"

    async def test_an_unknown_status_is_refused(self, db_session):
        clinician, patient = await _people(db_session)
        db_session.add(_row(clinician, patient, status="finalised"))

        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_an_amendment_cannot_be_recorded_without_a_reason(self, db_session):
        """An amendment with no reason is a change nobody has to justify."""
        clinician, patient = await _people(db_session)
        db_session.add(
            _row(
                clinician,
                patient,
                status="amended",
                signed_at=datetime(2026, 9, 6, 10, 0),
                signed_by=clinician.id,
                amended_at=datetime(2026, 9, 6, 11, 0),
                amendment_reason="",
            )
        )

        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_an_unknown_note_source_is_refused(self, db_session):
        clinician, patient = await _people(db_session)
        db_session.add(_row(clinician, patient, note_source="magic"))

        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_an_order_of_an_unknown_kind_is_refused(self, db_session):
        """Nothing knows how to file it as work, so it must not exist."""
        clinician, patient = await _people(db_session)
        encounter = _row(clinician, patient)
        db_session.add(encounter)
        await db_session.flush()
        db_session.add(
            EncounterOrder(id=str(uuid4()), encounter_id=encounter.id, kind="surgery", detail="algo")
        )

        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_a_deadline_in_the_past_is_refused(self, db_session):
        clinician, patient = await _people(db_session)
        encounter = _row(clinician, patient)
        db_session.add(encounter)
        await db_session.flush()
        db_session.add(
            EncounterOrder(
                id=str(uuid4()),
                encounter_id=encounter.id,
                kind="lab",
                detail="Potasio",
                due_in_days=0,
            )
        )

        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()


class TestEncryptedColumns:
    async def test_the_narrative_round_trips_through_encryption(self, db_session):
        """Free clinical text goes through the PHI column types (ADR-014), so
        a database dump without the key is not a chart."""
        clinician, patient = await _people(db_session)
        db_session.add(
            _row(
                clinician,
                patient,
                chief_complaint="Cefalea occipital",
                subjective="Tres días de evolución",
                assessment="Crisis hipertensiva",
                patient_instructions="Volver si empeora",
            )
        )
        await db_session.flush()
        db_session.expire_all()

        stored = (await db_session.scalars(select(Encounter))).one()
        assert stored.chief_complaint == "Cefalea occipital"
        assert stored.subjective == "Tres días de evolución"
        assert stored.assessment == "Crisis hipertensiva"
        assert stored.patient_instructions == "Volver si empeora"

    async def test_vitals_round_trip_as_a_dict(self, db_session):
        clinician, patient = await _people(db_session)
        db_session.add(_row(clinician, patient, vitals={"systolic": 210.0, "diastolic": 120.0}))
        await db_session.flush()
        db_session.expire_all()

        stored = (await db_session.scalars(select(Encounter))).one()
        assert stored.vitals == {"systolic": 210.0, "diastolic": 120.0}

    async def test_an_order_detail_is_encrypted_too(self, db_session):
        clinician, patient = await _people(db_session)
        encounter = _row(clinician, patient)
        db_session.add(encounter)
        await db_session.flush()
        db_session.add(
            EncounterOrder(
                id=str(uuid4()),
                encounter_id=encounter.id,
                kind="lab",
                detail="Potasio sérico en una semana",
            )
        )
        await db_session.flush()
        db_session.expire_all()

        stored = (await db_session.scalars(select(EncounterOrder))).one()
        assert stored.detail == "Potasio sérico en una semana"


class TestDefaults:
    async def test_a_new_encounter_starts_as_an_editable_draft(self, db_session):
        clinician, patient = await _people(db_session)
        db_session.add(_row(clinician, patient))
        await db_session.flush()

        stored = (await db_session.scalars(select(Encounter))).one()
        assert stored.status == "draft"
        assert stored.note_source == "clinician"
        assert stored.specialty == "general"
        assert stored.clinical_note_id is None
        assert stored.vitals == {}
