"""Derived tasks: created once, and retired when their reason goes away.

Persisting work that used to be re-derived on every page load buys an
assignee, a due date and a history, and costs the one thing the derived list
had for free — when the condition stops holding, the row does not disappear on
its own. These tests hold both halves: running the sweep repeatedly must not
accumulate, and a condition that resolves must retire its task.

Verifies AC-018-12, AC-018-13, AC-018-14
(docs/specs/SPEC-018-unified-tasks.md).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.services import task_service as svc
from api.services.task_derivation import sync_derived_tasks
from data.schemas import ImagingStudy, LabResult, Patient, PendingAction, Task, User

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 12, 0, 0)


async def _patient(session, pid="PD1", meds=None):
    p = Patient(
        id=pid,
        name="Ana Ruiz",
        age=54,
        sex="F",
        medical_record_number=f"MRN-{pid}",
        medications=meds or [],
    )
    session.add(p)
    await session.flush()
    return p


async def _critical_lab(session, patient_id, test_name="Potasio", value="6.8"):
    row = LabResult(
        patient_id=patient_id,
        test_name=test_name,
        value=value,
        unit="mmol/L",
        taken_at=NOW - timedelta(hours=2),
        is_abnormal=True,
        is_critical=True,
    )
    session.add(row)
    await session.flush()
    return row


async def _open_tasks(session):
    return list((await session.scalars(select(Task).where(Task.status.in_(svc.OPEN_STATUSES)))).all())


class TestIdempotency:
    async def test_three_sweeps_produce_n_tasks_not_three_n(self, db_session):
        """The tick runs every five minutes. If the sweep were not keyed on the
        condition, a day would end with 288 copies of the same finding."""
        patient = await _patient(db_session)
        await _critical_lab(db_session, patient.id)
        db_session.add(
            ImagingStudy(
                id=str(uuid4()),
                patient_id=patient.id,
                modality="CT",
                body_part="tórax",
                severity="critical",
                study_date=NOW - timedelta(days=1),
            )
        )
        await db_session.flush()

        first = await sync_derived_tasks(db_session, NOW)
        after_first = len(await _open_tasks(db_session))

        second = await sync_derived_tasks(db_session, NOW + timedelta(minutes=5))
        third = await sync_derived_tasks(db_session, NOW + timedelta(minutes=10))

        assert first["created"] == after_first > 0
        assert second["created"] == 0
        assert third["created"] == 0
        assert len(await _open_tasks(db_session)) == after_first

    async def test_a_drug_pair_is_one_finding_regardless_of_order(self, db_session):
        """warfarin+aspirin and aspirin+warfarin are the same clinical fact;
        keying on the unsorted pair would file it twice."""
        from api.services.task_derivation import _interaction_key

        assert _interaction_key("P1", "Warfarina", "aspirina") == _interaction_key(
            "P1", "Aspirina", "warfarina"
        )

    async def test_a_new_critical_value_is_new_work_not_an_update(self, db_session):
        patient = await _patient(db_session)
        await _critical_lab(db_session, patient.id, value="6.8")
        await sync_derived_tasks(db_session, NOW)
        before = len(await _open_tasks(db_session))

        # A second, later critical reading of the same test.
        newer = LabResult(
            patient_id=patient.id,
            test_name="Potasio",
            value="7.4",
            unit="mmol/L",
            taken_at=NOW - timedelta(minutes=30),
            is_abnormal=True,
            is_critical=True,
        )
        db_session.add(newer)
        await db_session.flush()

        await sync_derived_tasks(db_session, NOW + timedelta(minutes=5))
        open_now = await _open_tasks(db_session)

        # The old task is retired (that measurement is no longer the latest)
        # and the new value files its own, rather than silently mutating the
        # first one's title under a clinician who already read it.
        assert len(open_now) == before
        assert any("7.4" in t.title for t in open_now)


class TestRetirement:
    async def test_a_resolved_condition_supersedes_its_task(self, db_session):
        patient = await _patient(db_session)
        lab = await _critical_lab(db_session, patient.id)
        await sync_derived_tasks(db_session, NOW)
        task = (await _open_tasks(db_session))[0]

        # The repeat draw comes back normal.
        lab.is_critical = False
        await db_session.flush()
        result = await sync_derived_tasks(db_session, NOW + timedelta(minutes=5))

        # The service never commits (see the package docstring), so the test
        # flushes before re-reading -- refresh() alone would re-SELECT over the
        # pending change and report the stale row.
        await db_session.flush()
        await db_session.refresh(task)
        assert result["superseded"] == 1
        assert task.status == "superseded"

    async def test_a_retired_task_is_not_resurrected_by_the_next_sweep(self, db_session):
        patient = await _patient(db_session)
        lab = await _critical_lab(db_session, patient.id)
        await sync_derived_tasks(db_session, NOW)
        lab.is_critical = False
        await db_session.flush()
        await sync_derived_tasks(db_session, NOW + timedelta(minutes=5))

        # The same condition returns — but as the same measurement, so its key
        # is unchanged. `create_task` must not revive work a clinician already
        # saw the end of.
        lab.is_critical = True
        await db_session.flush()
        await sync_derived_tasks(db_session, NOW + timedelta(minutes=10))

        rows = (await db_session.scalars(select(Task))).all()
        assert len(rows) == 1
        assert rows[0].status == "superseded"

    async def test_the_sweep_never_touches_tasks_it_does_not_own(self, db_session):
        """Superseding an alert task because no derivation rule re-created it
        would silently close real work."""
        patient = await _patient(db_session)
        alert_task, _ = await svc.create_task(
            db_session,
            source_type="alert",
            source_id=str(uuid4()),
            category="alert",
            severity="high",
            title="Alerta real",
            dedupe_key=f"alert:{uuid4()}",
            patient_id=patient.id,
            now=NOW,
        )
        await db_session.flush()

        await sync_derived_tasks(db_session, NOW)

        await db_session.refresh(alert_task)
        assert alert_task.status == "open"


class TestSourceBackedDerivation:
    async def test_a_pending_approval_inherits_its_own_deadline(self, db_session):
        """An approval that expires in 14 days is not "due in 24 hours"
        because the severity table says so — the source's deadline wins."""
        patient = await _patient(db_session)
        expires = NOW + timedelta(days=14)
        db_session.add(
            PendingAction(
                id="PA-D1",
                patient_id=patient.id,
                action_type="followup_check",
                draft_text="¿Cómo seguís?",
                expires_at=expires,
            )
        )
        await db_session.flush()

        await sync_derived_tasks(db_session, NOW)

        task = (await db_session.scalars(select(Task).where(Task.category == "approval"))).one()
        assert task.due_at == expires
        assert task.source_id == "PA-D1"

    async def test_an_approval_that_closes_is_reconciled_away(self, db_session):
        """`approvals.py::_expire_due_pending` is a bulk UPDATE that bypasses
        every Python hook — the tick sweep is the only thing that notices."""
        from api.services.task_adapters import reconcile_tasks

        patient = await _patient(db_session)
        action = PendingAction(
            id="PA-D2",
            patient_id=patient.id,
            action_type="followup_check",
            draft_text="x",
        )
        db_session.add(action)
        await db_session.flush()
        await sync_derived_tasks(db_session, NOW)
        task = (await db_session.scalars(select(Task).where(Task.category == "approval"))).one()

        reviewer = User(
            id=str(uuid4()),
            email=f"{uuid4().hex[:8]}@example.test",
            name="Dra. R",
            hashed_password="x",
            role="clinician",
        )
        db_session.add(reviewer)
        await db_session.flush()
        action.status = "expired"
        await db_session.flush()

        superseded = await reconcile_tasks(db_session, NOW + timedelta(minutes=5))

        await db_session.flush()
        await db_session.refresh(task)
        assert superseded == 1
        assert task.status == "superseded"
