"""`appointment_reminder` workflow definition (SPEC-012): NEW_APPOINTMENT
subscriber + T-24h reminder handler + T-2h unconfirmed-escalation
handler."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.workflows.appointment_reminder import (
    REMINDER_LEAD_TIME,
    UNCONFIRMED_LEAD_TIME,
    escalate_if_unconfirmed,
    on_new_appointment,
    send_reminder_t24,
)
from api.workflows.channels import get_channel
from api.workflows.registry import StepContext
from data.schemas import Alert, Appointment, Notification, Patient, User, Workflow, WorkflowStep
from sephiroth.workflows.events import NEW_APPOINTMENT, emit

pytestmark = pytest.mark.asyncio

START_AT = datetime(2026, 9, 1, 10, 0, 0)


async def _patient_with_login(session, pid="PAPT1"):
    p = Patient(id=pid, name="Reminder Patient", age=40, sex="F", medical_record_number=f"PT-{pid}")
    session.add(p)
    u = User(
        id=str(uuid4()), email=f"{uuid4().hex[:8]}@example.org", name="Portal Patient",
        hashed_password="x", role="patient", patient_id=pid,
    )
    session.add(u)
    await session.commit()
    return p, u


async def _clinician_user(session):
    u = User(id=str(uuid4()), email=f"{uuid4().hex[:8]}@example.org", name="Dr. Book", hashed_password="x", role="clinician")
    session.add(u)
    await session.commit()
    return u


async def _appointment(session, patient_id, clinician_id, start_at=START_AT, status="booked"):
    appt = Appointment(
        id=str(uuid4()), clinician_id=clinician_id, patient_id=patient_id,
        start_at=start_at, end_at=start_at + timedelta(minutes=30), status=status,
    )
    session.add(appt)
    await session.commit()
    return appt


async def test_on_new_appointment_enrolls_two_steps_at_correct_offsets(db_session):
    patient, _ = await _patient_with_login(db_session)
    clinician = await _clinician_user(db_session)
    appt = await _appointment(db_session, patient.id, clinician.id)
    event = emit(db_session, NEW_APPOINTMENT, "appointment", appt.id, patient_id=patient.id)
    await db_session.commit()

    await on_new_appointment(db_session, event)
    await db_session.commit()

    workflow = (await db_session.scalars(select(Workflow).where(Workflow.appointment_id == appt.id))).one()
    steps = {
        s.step_key: s
        for s in (await db_session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id))).all()
    }
    assert set(steps) == {"reminder_t24", "unconfirmed_check"}
    assert steps["reminder_t24"].due_at == appt.start_at - REMINDER_LEAD_TIME
    assert steps["unconfirmed_check"].due_at == appt.start_at - UNCONFIRMED_LEAD_TIME


async def test_on_new_appointment_is_idempotent(db_session):
    patient, _ = await _patient_with_login(db_session)
    clinician = await _clinician_user(db_session)
    appt = await _appointment(db_session, patient.id, clinician.id)
    event = emit(db_session, NEW_APPOINTMENT, "appointment", appt.id, patient_id=patient.id)
    await db_session.commit()

    await on_new_appointment(db_session, event)
    await db_session.commit()
    await on_new_appointment(db_session, event)
    await db_session.commit()

    workflows = (await db_session.scalars(select(Workflow).where(Workflow.appointment_id == appt.id))).all()
    assert len(workflows) == 1


async def test_send_reminder_t24_notifies_patient(db_session):
    patient, login = await _patient_with_login(db_session)
    clinician = await _clinician_user(db_session)
    appt = await _appointment(db_session, patient.id, clinician.id)
    workflow = Workflow(
        id=str(uuid4()), definition_key="appointment_reminder", patient_id=patient.id, appointment_id=appt.id,
        status="active", context={"start_at": appt.start_at.isoformat()},
    )
    db_session.add(workflow)
    await db_session.commit()
    step = WorkflowStep(
        id=str(uuid4()), workflow_id=workflow.id, step_key="reminder_t24", step_type="appointment_reminder_t24",
        status="running", due_at=appt.start_at - REMINDER_LEAD_TIME, run_after=appt.start_at - REMINDER_LEAD_TIME,
    )
    db_session.add(step)
    await db_session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx = StepContext(session=db_session, step=step, workflow=workflow, now=now, channel=get_channel())
    result = await send_reminder_t24(ctx)

    assert result.outcome == "succeeded"
    notifications = (await db_session.scalars(select(Notification).where(Notification.user_id == login.id))).all()
    assert len(notifications) == 1


async def test_send_reminder_t24_superseded_after_cancellation(db_session):
    patient, _ = await _patient_with_login(db_session)
    clinician = await _clinician_user(db_session)
    appt = await _appointment(db_session, patient.id, clinician.id)
    workflow = Workflow(
        id=str(uuid4()), definition_key="appointment_reminder", patient_id=patient.id, appointment_id=appt.id,
        status="active", context={"start_at": appt.start_at.isoformat()},
    )
    db_session.add(workflow)
    step = WorkflowStep(
        id=str(uuid4()), workflow_id=workflow.id, step_key="reminder_t24", step_type="appointment_reminder_t24",
        status="running", due_at=appt.start_at - REMINDER_LEAD_TIME, run_after=appt.start_at - REMINDER_LEAD_TIME,
    )
    db_session.add(step)
    appt.status = "cancelled"
    await db_session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx = StepContext(session=db_session, step=step, workflow=workflow, now=now, channel=get_channel())
    result = await send_reminder_t24(ctx)

    assert result.outcome == "superseded"


async def test_escalate_if_unconfirmed_creates_alert_when_not_confirmed(db_session):
    patient, _ = await _patient_with_login(db_session)
    clinician = await _clinician_user(db_session)
    appt = await _appointment(db_session, patient.id, clinician.id)
    workflow = Workflow(
        id=str(uuid4()), definition_key="appointment_reminder", patient_id=patient.id, appointment_id=appt.id,
        status="active", context={"start_at": appt.start_at.isoformat()},
    )
    db_session.add(workflow)
    step = WorkflowStep(
        id=str(uuid4()), workflow_id=workflow.id, step_key="unconfirmed_check", step_type="appointment_unconfirmed_check",
        status="running", due_at=appt.start_at - UNCONFIRMED_LEAD_TIME, run_after=appt.start_at - UNCONFIRMED_LEAD_TIME,
    )
    db_session.add(step)
    await db_session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx = StepContext(session=db_session, step=step, workflow=workflow, now=now, channel=get_channel())
    result = await escalate_if_unconfirmed(ctx)

    assert result.outcome == "succeeded"
    alerts = (await db_session.scalars(select(Alert).where(Alert.patient_id == patient.id))).all()
    assert len(alerts) == 1
    assert alerts[0].source == "appointment_engine"


async def test_escalate_if_unconfirmed_superseded_when_confirmed(db_session):
    patient, _ = await _patient_with_login(db_session)
    clinician = await _clinician_user(db_session)
    appt = await _appointment(db_session, patient.id, clinician.id)
    appt.confirmed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db_session.commit()
    workflow = Workflow(
        id=str(uuid4()), definition_key="appointment_reminder", patient_id=patient.id, appointment_id=appt.id,
        status="active", context={"start_at": appt.start_at.isoformat()},
    )
    db_session.add(workflow)
    step = WorkflowStep(
        id=str(uuid4()), workflow_id=workflow.id, step_key="unconfirmed_check", step_type="appointment_unconfirmed_check",
        status="running", due_at=appt.start_at - UNCONFIRMED_LEAD_TIME, run_after=appt.start_at - UNCONFIRMED_LEAD_TIME,
    )
    db_session.add(step)
    await db_session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx = StepContext(session=db_session, step=step, workflow=workflow, now=now, channel=get_channel())
    result = await escalate_if_unconfirmed(ctx)

    assert result.outcome == "superseded"
    alerts = (await db_session.scalars(select(Alert).where(Alert.patient_id == patient.id))).all()
    assert alerts == []
