"""Signing, and everything it sets in motion.

Signing is the only moment an encounter reaches the rest of the product: it
writes the `ClinicalNote` that lands in the chart. Before it, an encounter is
invisible — which is what makes the signature, rather than a separate approval
row, the review gate for AI-drafted content (ADR-016).

Idempotency gets its own class because signing is the one action a clinician
might double-click, and the cost of getting it wrong is a duplicate note in a
patient's chart.

Restoration note: the original version of this file also covered "signing
files one task per order" (TestSigningFilesTheWork, TestOrderDeadlines,
TestTheTaskItFiles) via the unified task inbox (SPEC-018). That system was
removed by the c7fbdf5 revert; `encounter_service._file_orders` is a
deliberate no-op until it's restored (see that module's docstring), so those
classes — and any assertion here that read `order.task_id` or queried `Task`
— are dropped rather than kept as tests that could never pass. Restore them
alongside the task inbox phase.

Verifies AC-023-03 (docs/specs/SPEC-023-clinical-encounter.md); AC-023-04
(order deadlines) is task-inbox territory and out of scope until then.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.services import encounter_service as svc
from data.schemas import ClinicalNote, Patient, User

pytestmark = pytest.mark.asyncio


async def _clinician(session, name="Dra. Ruiz"):
    user = User(
        id=str(uuid4()),
        email=f"{uuid4().hex[:8]}@example.org",
        name=name,
        hashed_password="x",
        role="clinician",
    )
    session.add(user)
    await session.flush()
    return user


async def _patient(session, pid=None):
    patient = Patient(
        id=pid or f"P{uuid4().hex[:6]}",
        name="Ana Gómez",
        age=61,
        sex="F",
        medical_record_number=f"MRN-{uuid4().hex[:6]}",
    )
    session.add(patient)
    await session.flush()
    return patient


async def _encounter(session, *, clinician=None, patient=None, **fields):
    clinician = clinician or await _clinician(session)
    patient = patient or await _patient(session)
    encounter = await svc.create_encounter(session, patient_id=patient.id, clinician=clinician, **fields)
    await session.flush()
    return encounter, clinician, patient


class TestSigningWritesTheNote:
    async def test_it_creates_exactly_one_clinical_note(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Cefalea")
        svc.update_encounter(encounter, {"assessment": "Crisis hipertensiva"})

        await svc.sign_encounter(db_session, encounter, signer=clinician)
        await db_session.flush()

        notes = (await db_session.scalars(select(ClinicalNote))).all()
        assert len(notes) == 1
        assert encounter.clinical_note_id == notes[0].id
        assert notes[0].note_type == "encounter"

    async def test_the_note_carries_the_rendered_narrative(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Cefalea")
        svc.update_encounter(
            encounter,
            {"vitals": {"systolic": "210", "diastolic": "120"}, "assessment": "Crisis hipertensiva"},
        )

        await svc.sign_encounter(db_session, encounter, signer=clinician)
        await db_session.flush()

        note = (await db_session.scalars(select(ClinicalNote))).one()
        assert "MOTIVO DE CONSULTA" in note.content
        assert "PA 210/120 mmHg" in note.content
        assert "Crisis hipertensiva" in note.content

    async def test_it_records_who_signed_and_when(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")

        moment = datetime(2026, 9, 6, 15, 30)
        await svc.sign_encounter(db_session, encounter, signer=clinician, now=moment)

        assert encounter.status == "signed"
        assert encounter.signed_by == clinician.id
        assert encounter.signed_at == moment

    async def test_an_encounter_with_nothing_written_cannot_be_signed(self, db_session):
        encounter, clinician, _ = await _encounter(db_session)

        with pytest.raises(svc.EncounterTransitionError):
            await svc.sign_encounter(db_session, encounter, signer=clinician)

    async def test_only_the_clinician_who_conducted_the_visit_may_sign(self, db_session):
        """A signature is a person standing behind clinical content. Somebody
        else's signature on it is a false record, not a convenience."""
        encounter, _own, _ = await _encounter(db_session, chief_complaint="Control")
        other = await _clinician(db_session, "Dr. Otro")

        with pytest.raises(svc.EncounterTransitionError) as exc:
            await svc.sign_encounter(db_session, encounter, signer=other)
        assert "conducted the visit" in str(exc.value)


class TestOrdersFileNoTaskYet:
    """Encounter.orders exist and are recorded, but `sign_encounter` files no
    task for them until the task inbox (SPEC-018) is restored — see this
    module's docstring."""

    async def test_an_encounter_with_no_orders_files_nothing(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")

        _e, task_ids = await svc.sign_encounter(db_session, encounter, signer=clinician)

        assert task_ids == []

    async def test_an_encounter_with_orders_still_files_nothing_for_now(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")
        await svc.add_order(db_session, encounter, kind="lab", detail="Potasio en una semana")
        await db_session.flush()

        _e, task_ids = await svc.sign_encounter(db_session, encounter, signer=clinician)

        assert task_ids == []


class TestSigningTwiceChangesNothing:
    """AC-023-03's second half. Signing is the one action a clinician might
    double-click."""

    async def test_a_second_sign_creates_no_second_note(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")

        await svc.sign_encounter(db_session, encounter, signer=clinician)
        await db_session.flush()
        first_note = encounter.clinical_note_id

        await svc.sign_encounter(db_session, encounter, signer=clinician)
        await db_session.flush()

        assert encounter.clinical_note_id == first_note
        assert len((await db_session.scalars(select(ClinicalNote))).all()) == 1

    async def test_a_second_sign_does_not_move_the_signature_time(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")
        first = datetime(2026, 9, 6, 9, 0)

        await svc.sign_encounter(db_session, encounter, signer=clinician, now=first)
        await svc.sign_encounter(db_session, encounter, signer=clinician, now=first + timedelta(hours=2))

        assert encounter.signed_at == first


class TestASignedEncounterIsClosed:
    async def test_it_cannot_be_edited(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")
        await svc.sign_encounter(db_session, encounter, signer=clinician)

        with pytest.raises(svc.EncounterTransitionError):
            svc.update_encounter(encounter, {"plan": "otra cosa"})

    async def test_it_cannot_take_new_orders(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")
        await svc.sign_encounter(db_session, encounter, signer=clinician)

        with pytest.raises(svc.EncounterTransitionError):
            await svc.add_order(db_session, encounter, kind="lab", detail="Tardío")

    async def test_amending_reopens_it_for_editing(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")
        await svc.sign_encounter(db_session, encounter, signer=clinician)

        await svc.amend_encounter(
            db_session, encounter, actor=clinician, reason="Corrijo la dosis", window_days=30
        )

        assert encounter.status == "amended"
        assert svc.is_editable(encounter)
        svc.update_encounter(encounter, {"plan": "Losartán 100mg"})

    async def test_an_amendment_needs_a_reason(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")
        await svc.sign_encounter(db_session, encounter, signer=clinician)

        with pytest.raises(svc.EncounterTransitionError):
            await svc.amend_encounter(db_session, encounter, actor=clinician, reason="  ", window_days=30)

    async def test_an_amendment_is_refused_after_the_window(self, db_session):
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")
        signed = datetime(2026, 1, 1, 9, 0)
        await svc.sign_encounter(db_session, encounter, signer=clinician, now=signed)

        with pytest.raises(svc.EncounterTransitionError) as exc:
            await svc.amend_encounter(
                db_session,
                encounter,
                actor=clinician,
                reason="tarde",
                window_days=30,
                now=signed + timedelta(days=31),
            )
        assert "window" in str(exc.value)

    async def test_an_amendment_writes_a_second_note_leaving_the_first_intact(self, db_session):
        """NG-5: the diff is not modelled, but what was first committed is not
        erased either."""
        encounter, clinician, _ = await _encounter(db_session, chief_complaint="Control")
        svc.update_encounter(encounter, {"assessment": "Primera impresión"})
        await svc.sign_encounter(db_session, encounter, signer=clinician)
        await db_session.flush()

        await svc.amend_encounter(db_session, encounter, actor=clinician, reason="corrección", window_days=30)
        svc.update_encounter(encounter, {"assessment": "Impresión corregida"})
        await svc.sign_encounter(db_session, encounter, signer=clinician)
        await db_session.flush()

        contents = [n.content for n in (await db_session.scalars(select(ClinicalNote))).all()]
        assert len(contents) == 2
        assert any("Primera impresión" in c for c in contents)
        assert any("Impresión corregida" in c for c in contents)


class TestOrdersOnADraft:
    async def test_an_order_needs_a_detail(self, db_session):
        encounter, _c, _p = await _encounter(db_session)
        with pytest.raises(svc.EncounterTransitionError):
            await svc.add_order(db_session, encounter, kind="lab", detail="   ")

    async def test_an_unknown_kind_is_refused(self, db_session):
        encounter, _c, _p = await _encounter(db_session)
        with pytest.raises(svc.EncounterTransitionError):
            await svc.add_order(db_session, encounter, kind="surgery", detail="algo")

    async def test_a_draft_order_can_be_removed(self, db_session):
        encounter, _c, _p = await _encounter(db_session)
        order = await svc.add_order(db_session, encounter, kind="lab", detail="Potasio")
        await db_session.flush()

        await svc.remove_order(db_session, encounter, order)

        assert await svc.list_orders(db_session, encounter) == []
