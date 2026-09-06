"""Recording a result.

Nothing created a `LabResult` before this phase: four modules read the table and
no code path wrote one, so every trend and every "recent results" panel was
reading a table that only ever filled from a fixture.

Two invariants get their own classes. A result can never exist without a
lifecycle — the thing ADR-017 moved out of the schema and into the service, so
the service is where it is proved. And the same measurement arriving twice is
the same measurement: a feed that retries must not put two potassiums in front
of a clinician.

Verifies AC-024-01, AC-024-03, AC-024-09 (docs/specs/SPEC-024-results-loop.md).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from api.services import result_service as svc
from data.schemas import LabResult, Patient, ResultReview, Task

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 9, 0)


async def _patient(session, **fields):
    patient = Patient(
        id=f"P{uuid4().hex[:6]}",
        name="Ana Gómez",
        age=61,
        sex="F",
        medical_record_number=f"MRN-{uuid4().hex[:6]}",
        **fields,
    )
    session.add(patient)
    await session.flush()
    return patient


async def _tasks(session):
    return (await session.scalars(select(Task).where(Task.source_type == "result_review"))).all()


class TestALabIsRecorded:
    async def test_it_writes_the_row_and_its_review(self, db_session):
        patient = await _patient(db_session)

        result, review, created = await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=6.2, unit="mEq/L", now=NOW
        )

        assert created is True
        assert result.test_name == "potassium"
        assert review.result_type == "lab"
        assert review.result_id == str(result.id)
        assert review.status == "received"

    async def test_a_result_can_never_exist_without_a_lifecycle(self, db_session):
        """ADR-017 moved this invariant out of the schema and into the service,
        so this is where it is proved."""
        patient = await _patient(db_session)
        for value in (4.1, 6.2, 2.9):
            await svc.record_lab_result(
                db_session,
                patient_id=patient.id,
                test_name="potassium",
                value=value,
                taken_at=NOW + timedelta(hours=value),
                now=NOW,
            )
        await db_session.flush()

        labs = await db_session.scalar(select(func.count()).select_from(LabResult))
        reviews = await db_session.scalar(select(func.count()).select_from(ResultReview))

        assert labs == reviews == 3

    async def test_the_classification_is_stored_with_its_reason(self, db_session):
        patient = await _patient(db_session)

        _r, review, _c = await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=6.2, now=NOW
        )

        assert review.severity == "critical"
        assert "5.5" in review.classification_reason

    async def test_the_stored_flags_match_the_classification(self, db_session):
        """`is_abnormal`/`is_critical` were columns nothing set. They are set
        now, from the same rule the review used, so the two cannot disagree."""
        patient = await _patient(db_session)

        result, _rev, _c = await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="creatinine", value=2.4, now=NOW
        )

        assert result.is_abnormal is True
        assert result.is_critical is False
        assert result.reference_high == 1.3

    async def test_a_supplied_range_is_kept_on_the_row(self, db_session):
        patient = await _patient(db_session)

        result, _rev, _c = await svc.record_lab_result(
            db_session,
            patient_id=patient.id,
            test_name="creatinine",
            value=0.5,
            reference_low=0.4,
            reference_high=1.1,
            now=NOW,
        )

        assert (result.reference_low, result.reference_high) == (0.4, 1.1)
        assert result.is_abnormal is False


class TestTheSameMeasurementTwice:
    """AC-024-01's second half."""

    async def test_a_retry_creates_no_second_review(self, db_session):
        patient = await _patient(db_session)
        taken = NOW - timedelta(hours=2)

        _r1, review1, created1 = await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=6.2, taken_at=taken, now=NOW
        )
        _r2, review2, created2 = await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=6.2, taken_at=taken, now=NOW
        )
        await db_session.flush()

        assert (created1, created2) == (True, False)
        assert review1.id == review2.id
        assert await db_session.scalar(select(func.count()).select_from(ResultReview)) == 1

    async def test_a_retry_files_no_second_task(self, db_session):
        patient = await _patient(db_session)
        taken = NOW - timedelta(hours=2)

        for _ in range(3):
            await svc.record_lab_result(
                db_session,
                patient_id=patient.id,
                test_name="potassium",
                value=6.2,
                taken_at=taken,
                now=NOW,
            )
        await db_session.flush()

        assert len(await _tasks(db_session)) == 1

    async def test_the_same_test_at_a_different_time_is_a_different_result(self, db_session):
        """A potassium drawn this morning and one drawn last week are two
        measurements, and a trend needs both."""
        patient = await _patient(db_session)

        await svc.record_lab_result(
            db_session,
            patient_id=patient.id,
            test_name="potassium",
            value=6.2,
            taken_at=NOW - timedelta(days=7),
            now=NOW,
        )
        await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=5.9, taken_at=NOW, now=NOW
        )
        await db_session.flush()

        assert await db_session.scalar(select(func.count()).select_from(LabResult)) == 2


class TestWorkCreated:
    """AC-024-03 — the gap this phase closes. Only *critical* results became
    work before; the creatinine that drifted up produced nothing at all, and
    those are the results that get missed precisely because they do not shout."""

    async def test_a_critical_result_becomes_urgent_work(self, db_session):
        patient = await _patient(db_session)

        _r, review, _c = await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=6.2, now=NOW
        )
        await db_session.flush()

        (task,) = await _tasks(db_session)
        assert task.severity == "critical"
        assert task.id == review.task_id
        assert "crítico" in task.title

    async def test_an_abnormal_result_becomes_work_too(self, db_session):
        patient = await _patient(db_session)

        await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="creatinine", value=2.4, now=NOW
        )
        await db_session.flush()

        (task,) = await _tasks(db_session)
        assert task.severity == "medium"

    async def test_a_normal_result_becomes_nothing(self, db_session):
        patient = await _patient(db_session)

        _r, review, _c = await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=4.1, now=NOW
        )
        await db_session.flush()

        assert await _tasks(db_session) == []
        assert review.task_id is None

    async def test_an_unclassifiable_result_becomes_low_priority_work(self, db_session):
        """Somebody has to look at a number nothing can judge."""
        patient = await _patient(db_session)

        await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="ferritina", value=300.0, now=NOW
        )
        await db_session.flush()

        (task,) = await _tasks(db_session)
        assert task.severity == "low"
        assert "rango de referencia" in task.title

    async def test_the_task_points_back_at_the_result(self, db_session):
        patient = await _patient(db_session)

        result, review, _c = await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=6.2, now=NOW
        )
        await db_session.flush()

        (task,) = await _tasks(db_session)
        assert task.context["result_type"] == "lab"
        assert task.context["result_id"] == str(result.id)
        assert task.dedupe_key == f"result_review:{review.id}"


class TestThePanelStaysInStep:
    """AC-024-09. Two representations of one lab value exist — the JSON panel
    the risk engine reads and the table everything else reads — and they were
    free to disagree because nothing wrote both."""

    async def test_recording_a_lab_updates_the_panel(self, db_session):
        patient = await _patient(db_session, lab_results={})

        await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=6.2, now=NOW
        )
        await db_session.flush()

        assert patient.lab_results["potassium"] == "6.2"

    async def test_the_panel_uses_the_normalised_name(self, db_session):
        """So the risk engine, which keys on `potassium`, finds a result
        recorded as "K+"."""
        patient = await _patient(db_session, lab_results={})

        await svc.record_lab_result(db_session, patient_id=patient.id, test_name="K+", value=6.2, now=NOW)
        await db_session.flush()

        assert "potassium" in patient.lab_results

    async def test_the_risk_engine_now_sees_what_was_recorded(self, db_session):
        """The point of the write: a critical result and the alert it should
        raise stop disagreeing about the current value."""
        from sephiroth.safety.risk import assess_patient_risk

        patient = await _patient(db_session, lab_results={}, medications=[], allergies=[])
        await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=6.2, now=NOW
        )
        await db_session.flush()

        flags = assess_patient_risk(patient.lab_results, patient.medications, patient.allergies)

        assert any(flag["rule_key"] == "lab.potassium.high" for flag in flags)

    async def test_a_later_result_replaces_the_earlier_value(self, db_session):
        patient = await _patient(db_session, lab_results={})

        await svc.record_lab_result(
            db_session,
            patient_id=patient.id,
            test_name="potassium",
            value=6.2,
            taken_at=NOW - timedelta(days=1),
            now=NOW,
        )
        await svc.record_lab_result(
            db_session, patient_id=patient.id, test_name="potassium", value=4.4, taken_at=NOW, now=NOW
        )
        await db_session.flush()

        assert patient.lab_results["potassium"] == "4.4"


class TestImagingIntake:
    async def test_a_study_is_recorded_with_its_review(self, db_session):
        patient = await _patient(db_session)

        study, review, created = await svc.record_imaging_study(
            db_session,
            patient_id=patient.id,
            modality="TAC",
            body_part="cráneo",
            severity="review",
            finding_summary="Nódulo de 8mm",
            now=NOW,
        )

        assert created is True
        assert review.result_type == "imaging"
        assert review.result_id == study.id
        assert review.severity == "abnormal"
        assert "Nódulo de 8mm" in review.classification_reason

    async def test_a_read_study_is_marked_analyzed(self, db_session):
        patient = await _patient(db_session)

        study, _rev, _c = await svc.record_imaging_study(
            db_session,
            patient_id=patient.id,
            modality="RX",
            body_part="tórax",
            severity="none",
            finding_summary="Sin hallazgos",
            now=NOW,
        )

        assert study.status == "analyzed"
        assert study.analyzed_at == NOW

    async def test_an_unread_study_stays_pending(self, db_session):
        patient = await _patient(db_session)

        study, _rev, _c = await svc.record_imaging_study(
            db_session, patient_id=patient.id, modality="RX", body_part="tórax", now=NOW
        )

        assert study.status == "pending"
        assert study.analyzed_at is None

    async def test_a_normal_study_becomes_no_work(self, db_session):
        patient = await _patient(db_session)

        await svc.record_imaging_study(
            db_session,
            patient_id=patient.id,
            modality="RX",
            body_part="tórax",
            severity="none",
            finding_summary="Sin hallazgos",
            now=NOW,
        )
        await db_session.flush()

        assert await _tasks(db_session) == []

    async def test_a_critical_study_becomes_urgent_work_in_the_imaging_category(self, db_session):
        patient = await _patient(db_session)

        await svc.record_imaging_study(
            db_session,
            patient_id=patient.id,
            modality="TAC",
            body_part="cráneo",
            severity="critical",
            finding_summary="Hemorragia",
            now=NOW,
        )
        await db_session.flush()

        (task,) = await _tasks(db_session)
        assert task.severity == "critical"
        assert task.category == "imaging"
