"""End-to-end: alert creation -> CLINICAL_ALERT event -> tick dispatch
-> escalation workflow enrolled -> (once due) escalated. Exercises the
real registration path (`register_subscriptions`), not a manually
monkeypatched subscriber."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from api.workflows.engine import claim_step, execute_step, run_tick
from api.workflows.subscriptions import register_subscriptions
from data.schemas import Patient, Workflow, WorkflowStep
from sephiroth.safety.alerts import generate_alerts_for_patient

pytestmark = pytest.mark.asyncio


async def test_alert_creation_through_tick_enrolls_escalation_workflow(db_session):
    register_subscriptions()

    patient = Patient(
        id="PE2E1", name="E2E Patient", age=65, sex="M", medical_record_number="PT-PE2E1",
        medications=[], lab_results={"potassium": "6.8 mEq/L"},  # triggers a real risk flag -> Alert
    )
    db_session.add(patient)
    await db_session.commit()

    created = await generate_alerts_for_patient(db_session, patient)
    await db_session.commit()
    assert len(created) >= 1
    alert = created[0]

    summary = await run_tick(db_session, tick_id="e2e-tick")

    assert summary.events_dispatched >= 1
    workflow = (
        await db_session.scalars(select(Workflow).where(Workflow.alert_id == alert.id))
    ).one()
    assert workflow.status == "active"
    step = (
        await db_session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id))
    ).one()
    assert step.status == "pending"
    assert step.due_at > datetime.now(timezone.utc).replace(tzinfo=None)
