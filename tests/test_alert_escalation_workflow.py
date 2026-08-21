"""`alert_escalation` workflow definition (SPEC-011): the CLINICAL_ALERT
subscriber + the escalate_if_unresolved step handler."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.workflows.alert_escalation import ESCALATION_WINDOW_BY_SEVERITY, escalate_if_unresolved, on_clinical_alert
from api.workflows.channels import get_channel
from api.workflows.registry import StepContext
from data.schemas import Alert, Notification, Patient, User, Workflow, WorkflowStep
from sephiroth.workflows.events import CLINICAL_ALERT, emit

pytestmark = pytest.mark.asyncio


async def _patient(session, pid="PESC1"):
    p = Patient(id=pid, name="Escalation Patient", age=55, sex="F", medical_record_number=f"PT-{pid}")
    session.add(p)
    await session.commit()
    return p


async def _alert(session, patient_id, severity="critical", status="active"):
    a = Alert(
        id=str(uuid4()), patient_id=patient_id, category="lab", severity=severity, status=status,
        title="Test alert", detail="", source="risk_engine",
    )
    session.add(a)
    await session.commit()
    return a


async def _clinician_user(session):
    u = User(
        id=str(uuid4()), email=f"{uuid4().hex[:8]}@example.org", name="Dr. Escalate",
        hashed_password="x", role="clinician", is_active=True,
    )
    session.add(u)
    await session.commit()
    return u


async def test_on_clinical_alert_creates_workflow_with_correct_due_date(db_session):
    patient = await _patient(db_session)
    alert = await _alert(db_session, patient.id, severity="critical")
    event = emit(db_session, CLINICAL_ALERT, "alert", alert.id, patient_id=patient.id)
    await db_session.commit()

    await on_clinical_alert(db_session, event)
    await db_session.commit()

    workflow = (
        await db_session.scalars(select(Workflow).where(Workflow.alert_id == alert.id))
    ).one()
    step = (
        await db_session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id))
    ).one()
    assert workflow.definition_key == "alert_escalation"
    assert step.step_type == "alert_escalate_check"
    expected_window = ESCALATION_WINDOW_BY_SEVERITY["critical"]
    assert abs((step.due_at - workflow.created_at).total_seconds() - expected_window.total_seconds()) < 5


async def test_on_clinical_alert_is_idempotent(db_session):
    patient = await _patient(db_session)
    alert = await _alert(db_session, patient.id)
    event = emit(db_session, CLINICAL_ALERT, "alert", alert.id, patient_id=patient.id)
    await db_session.commit()

    await on_clinical_alert(db_session, event)
    await db_session.commit()
    await on_clinical_alert(db_session, event)  # simulate a second dispatch attempt
    await db_session.commit()

    workflows = (await db_session.scalars(select(Workflow).where(Workflow.alert_id == alert.id))).all()
    assert len(workflows) == 1


async def test_on_clinical_alert_skips_already_resolved_alert(db_session):
    patient = await _patient(db_session)
    alert = await _alert(db_session, patient.id, status="resolved")
    event = emit(db_session, CLINICAL_ALERT, "alert", alert.id, patient_id=patient.id)
    await db_session.commit()

    await on_clinical_alert(db_session, event)
    await db_session.commit()

    workflows = (await db_session.scalars(select(Workflow).where(Workflow.alert_id == alert.id))).all()
    assert workflows == []


async def test_escalate_if_unresolved_notifies_active_clinicians(db_session):
    patient = await _patient(db_session)
    alert = await _alert(db_session, patient.id)
    clinician = await _clinician_user(db_session)
    workflow = Workflow(id=str(uuid4()), definition_key="alert_escalation", patient_id=patient.id, alert_id=alert.id, status="active")
    db_session.add(workflow)
    await db_session.commit()
    step = WorkflowStep(
        id=str(uuid4()), workflow_id=workflow.id, step_key="escalate_check", step_type="alert_escalate_check",
        status="running", due_at=datetime(2026, 1, 1), run_after=datetime(2026, 1, 1),
    )
    db_session.add(step)
    await db_session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx = StepContext(session=db_session, step=step, workflow=workflow, now=now, channel=get_channel())

    result = await escalate_if_unresolved(ctx)

    assert result.outcome == "succeeded"
    refreshed_alert = await db_session.get(Alert, alert.id)
    assert refreshed_alert.escalated_at == now
    notifications = (
        await db_session.scalars(select(Notification).where(Notification.user_id == clinician.id))
    ).all()
    assert len(notifications) == 1
    assert "escalated" in notifications[0].message.lower()


async def test_escalate_if_unresolved_is_superseded_when_already_reviewed(db_session):
    patient = await _patient(db_session)
    alert = await _alert(db_session, patient.id, status="reviewed")
    workflow = Workflow(id=str(uuid4()), definition_key="alert_escalation", patient_id=patient.id, alert_id=alert.id, status="active")
    db_session.add(workflow)
    await db_session.commit()
    step = WorkflowStep(
        id=str(uuid4()), workflow_id=workflow.id, step_key="escalate_check", step_type="alert_escalate_check",
        status="running", due_at=datetime(2026, 1, 1), run_after=datetime(2026, 1, 1),
    )
    db_session.add(step)
    await db_session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx = StepContext(session=db_session, step=step, workflow=workflow, now=now, channel=get_channel())

    result = await escalate_if_unresolved(ctx)

    assert result.outcome == "superseded"
    refreshed_alert = await db_session.get(Alert, alert.id)
    assert refreshed_alert.escalated_at is None
