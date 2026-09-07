"""Event catalog (SPEC-010) — outbox recording + dispatch-to-registry."""

import pytest
from sqlalchemy import select

from data.schemas import Patient
from sephiroth.workflows import events as workflow_events

pytestmark = pytest.mark.asyncio


async def _patient(session, pid="PEV1"):
    p = Patient(id=pid, name="Event Patient", age=45, sex="F", medical_record_number=f"PT-{pid}")
    session.add(p)
    await session.commit()
    return p


async def test_emit_stages_row_that_rollback_discards(db_session):
    from data.schemas import WorkflowEvent

    patient = await _patient(db_session)
    event = workflow_events.emit(
        db_session, workflow_events.NEW_APPOINTMENT, "appointment", "A1", patient_id=patient.id
    )
    await db_session.flush()
    assert event.status == "pending"  # Python-side default, applied on flush/insert

    # emit() never commits -- the same-transaction guarantee (SPEC-010): a
    # caller that rolls back (e.g. a booking conflict) leaves no event row.
    await db_session.rollback()

    remaining = (await db_session.scalars(select(WorkflowEvent))).all()
    assert remaining == []


async def test_dispatch_pending_marks_no_subscriber_when_unwired(db_session):
    # A reserved-but-genuinely-unwired event type: unlike CLINICAL_ALERT
    # (which Phase 9's register_subscriptions() may have already wired
    # elsewhere in this same test process -- SUBSCRIBERS is module-global
    # state), PATIENT_MESSAGE has no subscriber anywhere in the codebase.
    patient = await _patient(db_session)
    workflow_events.emit(db_session, workflow_events.PATIENT_MESSAGE, "message", "M1", patient_id=patient.id)
    await db_session.commit()

    from data.schemas import WorkflowEvent

    processed = await workflow_events.dispatch_pending(db_session)

    assert processed == 1
    row = (await db_session.scalars(select(WorkflowEvent))).one()
    assert row.status == "no_subscriber"
    assert row.dispatched_at is None  # only set when a real handler runs -- see below


async def test_dispatch_pending_runs_registered_subscriber(db_session, monkeypatch):
    from data.schemas import WorkflowEvent

    calls = []

    async def _handler(session, event):
        calls.append(event.id)

    monkeypatch.setitem(workflow_events.SUBSCRIBERS, "TEST_EVENT", [_handler])

    patient = await _patient(db_session)
    event = workflow_events.emit(db_session, "TEST_EVENT", "test", "T1", patient_id=patient.id)
    await db_session.commit()

    processed = await workflow_events.dispatch_pending(db_session)

    assert processed == 1
    assert calls == [event.id]
    row = await db_session.get(WorkflowEvent, event.id)
    assert row.status == "dispatched"


async def test_dispatch_pending_is_idempotent_no_double_processing(db_session):
    patient = await _patient(db_session)
    workflow_events.emit(
        db_session, workflow_events.LAB_RESULT_AVAILABLE, "result_share", "R1", patient_id=patient.id
    )
    await db_session.commit()

    first = await workflow_events.dispatch_pending(db_session)
    second = await workflow_events.dispatch_pending(db_session)

    assert first == 1
    assert second == 0  # already dispatched/no_subscriber, not re-selected
