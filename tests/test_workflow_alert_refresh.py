"""`alert_refresh` — the proof-of-life step type for SPEC-009. Exercises
seeding + the handler end to end, and asserts running it twice creates
no duplicate `Alert` (AC-009-09)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.workflows.engine import claim_step, execute_step
from api.workflows.instantiate import seed_alert_refresh_workflows
from data.schemas import Alert, Patient, Workflow, WorkflowStep

pytestmark = pytest.mark.asyncio


async def _patient_with_risk(session, pid="PAR1"):
    p = Patient(
        id=pid,
        name="Risk Patient",
        age=60,
        sex="M",
        medical_record_number=f"PT-{pid}",
        medications=["warfarin", "aspirin"],
        lab_results={},
    )
    session.add(p)
    await session.commit()
    return p


async def test_seed_alert_refresh_workflows_is_idempotent(db_session):
    await _patient_with_risk(db_session)

    first = await seed_alert_refresh_workflows(db_session)
    second = await seed_alert_refresh_workflows(db_session)

    assert first == 1
    assert second == 0  # already has an active alert_refresh workflow

    workflows = (await db_session.scalars(select(Workflow).where(Workflow.definition_key == "alert_refresh"))).all()
    assert len(workflows) == 1


async def test_alert_refresh_handler_runs_twice_without_duplicating_alerts(db_session):
    patient = await _patient_with_risk(db_session)
    await seed_alert_refresh_workflows(db_session)

    step = (await db_session.scalars(select(WorkflowStep).where(WorkflowStep.step_type == "alert_refresh"))).one()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    won = await claim_step(db_session, step.id, "tick-1", now, lease_seconds=120)
    assert won is True
    outcome_1 = await execute_step(db_session, step.id, now)
    assert outcome_1 == "succeeded"

    alerts_after_first = (await db_session.scalars(select(Alert).where(Alert.patient_id == patient.id))).all()

    # Re-arm the same step (simulating a second scheduled run) and execute again.
    step.status = "pending"
    step.run_after = now
    await db_session.commit()
    await claim_step(db_session, step.id, "tick-2", now, lease_seconds=120)
    outcome_2 = await execute_step(db_session, step.id, now)
    assert outcome_2 == "succeeded"

    alerts_after_second = (await db_session.scalars(select(Alert).where(Alert.patient_id == patient.id))).all()

    assert len(alerts_after_second) == len(alerts_after_first)  # no duplicate created


async def test_alert_refresh_superseded_when_patient_deleted(db_session):
    patient = await _patient_with_risk(db_session, pid="PAR2")
    await seed_alert_refresh_workflows(db_session)
    step = (
        await db_session.scalars(
            select(WorkflowStep)
            .join(Workflow, Workflow.id == WorkflowStep.workflow_id)
            .where(Workflow.patient_id == patient.id)
        )
    ).one()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await claim_step(db_session, step.id, "tick-1", now, lease_seconds=120)

    await db_session.delete(patient)
    await db_session.commit()

    outcome = await execute_step(db_session, step.id, now)
    assert outcome == "superseded"
