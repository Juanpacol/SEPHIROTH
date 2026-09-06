"""The loop: received → reviewed → communicated → closed.

`TestTheLoopCannotBeShortCircuited` is the phase. Every other state transition
here is bookkeeping; the guard that a result whose decision was "tell the
patient" cannot be closed until they have been told is the only thing that
makes these states mean anything. Without it they are decoration, and the
question a clinic gets sued over — who saw this and what did they do — still
has no answer.

Verifies AC-024-04, AC-024-05, AC-024-06, AC-024-07, AC-024-08
(docs/specs/SPEC-024-results-loop.md).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.services import result_service as svc
from data.schemas import Patient, ResultShare, Task, TimelineEvent, User

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 9, 0)


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


async def _setup(session, *, test_name="potassium", value=6.2):
    patient = Patient(
        id=f"P{uuid4().hex[:6]}",
        name="Ana Gómez",
        age=61,
        sex="F",
        medical_record_number=f"MRN-{uuid4().hex[:6]}",
    )
    session.add(patient)
    await session.flush()
    clinician = await _clinician(session)
    _result, review, _created = await svc.record_lab_result(
        session, patient_id=patient.id, test_name=test_name, value=value, now=NOW
    )
    await session.flush()
    return review, clinician, patient


async def _timeline_event(session, patient_id: str) -> TimelineEvent:
    event = TimelineEvent(
        patient_id=patient_id,
        date=NOW.date(),
        type="lab",
        title="Potasio 6.2",
        detail="",
    )
    session.add(event)
    await session.flush()
    return event


class TestReview:
    """AC-024-04."""

    async def test_it_records_who_decided_what_and_when(self, db_session):
        review, clinician, _p = await _setup(db_session)

        await svc.review_result(
            db_session,
            review,
            actor=clinician,
            disposition="action_taken",
            note="Suspendo el IECA y repito en 48h",
            now=NOW,
        )

        assert review.status == "reviewed"
        assert review.disposition == "action_taken"
        assert review.note == "Suspendo el IECA y repito en 48h"
        assert review.reviewed_by == clinician.id
        assert review.reviewed_at == NOW

    async def test_a_decision_other_than_normal_needs_a_note(self, db_session):
        review, clinician, _p = await _setup(db_session)

        with pytest.raises(svc.ResultTransitionError) as exc:
            await svc.review_result(
                db_session, review, actor=clinician, disposition="abnormal_expected", note="  "
            )
        assert "needs a note" in str(exc.value)

    async def test_a_normal_result_needs_no_justification(self, db_session):
        """Requiring one teaches people to type "ok", and an inbox full of "ok"
        looks like review without being it."""
        review, clinician, _p = await _setup(db_session, test_name="potassium", value=4.1)

        await svc.review_result(db_session, review, actor=clinician, disposition="normal", now=NOW)

        assert review.status == "reviewed"
        assert review.note == ""

    async def test_an_unknown_disposition_is_refused(self, db_session):
        review, clinician, _p = await _setup(db_session)

        with pytest.raises(svc.ResultTransitionError):
            await svc.review_result(db_session, review, actor=clinician, disposition="looks_fine", note="x")

    async def test_a_decision_can_be_changed_before_the_loop_moves_on(self, db_session):
        review, clinician, _p = await _setup(db_session)
        await svc.review_result(
            db_session, review, actor=clinician, disposition="abnormal_expected", note="Crónico"
        )

        await svc.review_result(
            db_session, review, actor=clinician, disposition="needs_patient_contact", note="Llamar"
        )

        assert review.disposition == "needs_patient_contact"

    async def test_a_closed_result_cannot_be_re_reviewed_in_place(self, db_session):
        review, clinician, _p = await _setup(db_session)
        await svc.review_result(db_session, review, actor=clinician, disposition="action_taken", note="Hecho")
        await svc.close_result(db_session, review, actor=clinician, now=NOW)

        with pytest.raises(svc.ResultTransitionError):
            await svc.review_result(db_session, review, actor=clinician, disposition="normal", note="")


class TestTheLoopCannotBeShortCircuited:
    """AC-024-05 — the guard this phase exists for."""

    async def test_a_result_needing_contact_cannot_be_closed(self, db_session):
        review, clinician, _p = await _setup(db_session)
        await svc.review_result(
            db_session,
            review,
            actor=clinician,
            disposition="needs_patient_contact",
            note="Hay que avisarle del potasio",
        )

        with pytest.raises(svc.ResultTransitionError) as exc:
            await svc.close_result(db_session, review, actor=clinician, now=NOW)

        assert "communicate it before closing" in str(exc.value)
        assert review.status == "reviewed"

    async def test_it_closes_once_the_patient_has_been_told(self, db_session):
        review, clinician, patient = await _setup(db_session)
        event = await _timeline_event(db_session, patient.id)
        await svc.review_result(
            db_session, review, actor=clinician, disposition="needs_patient_contact", note="Avisar"
        )

        await svc.communicate_result(
            db_session,
            review,
            actor=clinician,
            message="Su potasio está alto; por favor venga hoy.",
            timeline_event_id=event.id,
            now=NOW,
        )
        await svc.close_result(db_session, review, actor=clinician, now=NOW)

        assert review.status == "closed"

    async def test_an_unreviewed_result_cannot_be_closed(self, db_session):
        review, clinician, _p = await _setup(db_session)

        with pytest.raises(svc.ResultTransitionError) as exc:
            await svc.close_result(db_session, review, actor=clinician, now=NOW)

        assert "unreviewed" in str(exc.value)

    async def test_every_other_disposition_closes_directly(self, db_session):
        """The guard is narrow on purpose: it applies to the one decision that
        creates an obligation to somebody outside the building."""
        for disposition in ("normal", "abnormal_expected", "action_taken"):
            review, clinician, _p = await _setup(db_session)
            await svc.review_result(
                db_session, review, actor=clinician, disposition=disposition, note="razón"
            )

            await svc.close_result(db_session, review, actor=clinician, now=NOW)

            assert review.status == "closed", disposition


class TestCommunicate:
    """AC-024-06."""

    async def test_it_creates_a_share_the_review_points_at(self, db_session):
        review, clinician, patient = await _setup(db_session)
        event = await _timeline_event(db_session, patient.id)
        await svc.review_result(
            db_session, review, actor=clinician, disposition="needs_patient_contact", note="Avisar"
        )

        share = await svc.communicate_result(
            db_session,
            review,
            actor=clinician,
            message="Su potasio está alto.",
            timeline_event_id=event.id,
            now=NOW,
        )
        await db_session.flush()

        assert review.share_id == share.id
        assert review.status == "communicated"
        assert share.message == "Su potasio está alto."

    async def test_the_share_can_be_found_from_the_result(self, db_session):
        """The point of the new columns: "was this result communicated" becomes
        a question the result itself can answer."""
        review, clinician, patient = await _setup(db_session)
        event = await _timeline_event(db_session, patient.id)
        await svc.review_result(
            db_session, review, actor=clinician, disposition="needs_patient_contact", note="Avisar"
        )
        await svc.communicate_result(
            db_session, review, actor=clinician, message="Aviso", timeline_event_id=event.id, now=NOW
        )
        await db_session.flush()

        found = (
            await db_session.scalars(
                select(ResultShare).where(
                    ResultShare.result_type == "lab", ResultShare.result_id == review.result_id
                )
            )
        ).one()

        assert found.id == review.share_id

    async def test_an_unreviewed_result_cannot_be_communicated(self, db_session):
        """Telling a patient about a result nobody has read is the failure the
        whole loop exists to prevent."""
        review, clinician, patient = await _setup(db_session)
        event = await _timeline_event(db_session, patient.id)

        with pytest.raises(svc.ResultTransitionError) as exc:
            await svc.communicate_result(
                db_session, review, actor=clinician, message="x", timeline_event_id=event.id
            )
        assert "reviewed before" in str(exc.value)

    async def test_it_reuses_the_existing_sharing_path(self, db_session):
        """Rather than inventing a second way to send something to a patient —
        the portal already renders `ResultShare`."""
        review, clinician, patient = await _setup(db_session)
        event = await _timeline_event(db_session, patient.id)
        await svc.review_result(
            db_session, review, actor=clinician, disposition="needs_patient_contact", note="Avisar"
        )

        share = await svc.communicate_result(
            db_session, review, actor=clinician, message="Aviso", timeline_event_id=event.id, now=NOW
        )

        assert share.timeline_event_id == event.id
        assert share.status == "sent"


class TestClose:
    """AC-024-07."""

    async def test_it_records_who_closed_and_when(self, db_session):
        review, clinician, _p = await _setup(db_session)
        await svc.review_result(db_session, review, actor=clinician, disposition="action_taken", note="Hecho")

        await svc.close_result(db_session, review, actor=clinician, now=NOW)

        assert review.closed_by == clinician.id
        assert review.closed_at == NOW

    async def test_it_closes_the_task_the_result_raised(self, db_session):
        """Otherwise the inbox keeps asking for work somebody already did."""
        review, clinician, _p = await _setup(db_session)
        await svc.review_result(db_session, review, actor=clinician, disposition="action_taken", note="Hecho")

        await svc.close_result(db_session, review, actor=clinician, now=NOW)
        await db_session.flush()

        task = await db_session.get(Task, review.task_id)
        assert task.status == "done"
        assert task.closed_by == clinician.id

    async def test_a_normal_result_has_no_task_to_close(self, db_session):
        review, clinician, _p = await _setup(db_session, value=4.1)
        await svc.review_result(db_session, review, actor=clinician, disposition="normal")

        await svc.close_result(db_session, review, actor=clinician, now=NOW)

        assert review.status == "closed"
        assert review.task_id is None

    async def test_closing_twice_changes_nothing(self, db_session):
        review, clinician, _p = await _setup(db_session)
        await svc.review_result(db_session, review, actor=clinician, disposition="action_taken", note="Hecho")
        await svc.close_result(db_session, review, actor=clinician, now=NOW)

        await svc.close_result(db_session, review, actor=clinician, now=NOW + timedelta(hours=3))

        assert review.closed_at == NOW


class TestReopen:
    """AC-024-08."""

    async def test_it_returns_the_result_to_where_it_was(self, db_session):
        review, clinician, _p = await _setup(db_session)
        await svc.review_result(db_session, review, actor=clinician, disposition="action_taken", note="Hecho")
        await svc.close_result(db_session, review, actor=clinician, now=NOW)

        await svc.reopen_result(
            db_session, review, actor=clinician, window_days=30, now=NOW + timedelta(days=1)
        )

        assert review.status == "reviewed"
        assert review.closed_at is None

    async def test_a_communicated_result_reopens_as_communicated(self, db_session):
        """It was communicated; reopening does not un-tell the patient."""
        review, clinician, patient = await _setup(db_session)
        event = await _timeline_event(db_session, patient.id)
        await svc.review_result(
            db_session, review, actor=clinician, disposition="needs_patient_contact", note="Avisar"
        )
        await svc.communicate_result(
            db_session, review, actor=clinician, message="Aviso", timeline_event_id=event.id, now=NOW
        )
        await svc.close_result(db_session, review, actor=clinician, now=NOW)

        await svc.reopen_result(db_session, review, actor=clinician, window_days=30, now=NOW)

        assert review.status == "communicated"

    async def test_it_is_refused_outside_the_window(self, db_session):
        review, clinician, _p = await _setup(db_session)
        await svc.review_result(db_session, review, actor=clinician, disposition="action_taken", note="Hecho")
        await svc.close_result(db_session, review, actor=clinician, now=NOW)

        with pytest.raises(svc.ResultTransitionError) as exc:
            await svc.reopen_result(
                db_session, review, actor=clinician, window_days=30, now=NOW + timedelta(days=31)
            )
        assert "window" in str(exc.value)

    async def test_an_open_result_cannot_be_reopened(self, db_session):
        review, clinician, _p = await _setup(db_session)

        with pytest.raises(svc.ResultTransitionError):
            await svc.reopen_result(db_session, review, actor=clinician, window_days=30, now=NOW)


class TestTheInboxOrder:
    async def test_critical_comes_first_then_the_oldest(self, db_session):
        """The two things that decide what to open next."""
        patient = Patient(id="PORD1", name="Ana", age=61, sex="F", medical_record_number="MRN-PORD1")
        db_session.add(patient)
        await db_session.flush()

        await svc.record_lab_result(
            db_session,
            patient_id=patient.id,
            test_name="creatinine",
            value=2.4,
            taken_at=NOW - timedelta(days=3),
            now=NOW - timedelta(days=3),
        )
        await svc.record_lab_result(
            db_session,
            patient_id=patient.id,
            test_name="ferritina",
            value=300.0,
            taken_at=NOW - timedelta(days=2),
            now=NOW - timedelta(days=2),
        )
        await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=6.2, now=NOW
        )
        await db_session.flush()

        reviews = await svc.list_reviews(db_session)

        assert [r.severity for r in reviews] == ["critical", "abnormal", "unclassified"]

    async def test_a_closed_result_leaves_the_open_list(self, db_session):
        review, clinician, _p = await _setup(db_session)
        await svc.review_result(db_session, review, actor=clinician, disposition="action_taken", note="Hecho")
        await svc.close_result(db_session, review, actor=clinician, now=NOW)
        await db_session.flush()

        assert await svc.list_reviews(db_session, status=list(svc.OPEN_STATUSES)) == []
        assert len(await svc.list_reviews(db_session, status=["closed"])) == 1
