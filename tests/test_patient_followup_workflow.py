"""`patient_followup` workflow definition (SPEC-014): enrollment + the
day-3/7/30 step handler creating an empty-draft PendingAction."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.workflows.channels import get_channel
from api.workflows.patient_followup import CHECK_OFFSETS, enroll_plan, followup_check_due
from api.workflows.registry import StepContext
from data.schemas import FollowupPlan, Patient, PendingAction, User, Workflow, WorkflowStep

pytestmark = pytest.mark.asyncio

CREATED_AT = datetime(2026, 6, 1, 12, 0, 0)


async def _patient(session, pid="PFU1"):
    p = Patient(id=pid, name="Followup Patient", age=52, sex="M", medical_record_number=f"PT-{pid}")
    session.add(p)
    await session.commit()
    return p


async def _clinician(session):
    u = User(id=str(uuid4()), email=f"{uuid4().hex[:8]}@example.org", name="Dr. Followup", hashed_password="x", role="clinician")
    session.add(u)
    await session.commit()
    return u


async def test_enroll_plan_creates_three_steps_at_correct_offsets(db_session):
    patient = await _patient(db_session)
    clinician = await _clinician(db_session)
    plan = FollowupPlan(id=str(uuid4()), patient_id=patient.id, created_by_user_id=clinician.id, instructions="rest and hydrate", created_at=CREATED_AT)
    db_session.add(plan)
    await db_session.commit()

    workflow = await enroll_plan(db_session, plan)
    await db_session.commit()

    steps = {
        s.step_key: s
        for s in (await db_session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id))).all()
    }
    assert set(steps) == {"day3", "day7", "day30"}
    for key, offset in CHECK_OFFSETS.items():
        assert steps[key].due_at == CREATED_AT + offset
        assert steps[key].step_type == "followup_check_due"


async def test_followup_check_due_creates_empty_draft_pending_action(db_session):
    patient = await _patient(db_session)
    clinician = await _clinician(db_session)
    plan = FollowupPlan(id=str(uuid4()), patient_id=patient.id, created_by_user_id=clinician.id, created_at=CREATED_AT)
    db_session.add(plan)
    await db_session.commit()
    workflow = Workflow(id=str(uuid4()), definition_key="patient_followup", patient_id=patient.id, followup_plan_id=plan.id, status="active")
    db_session.add(workflow)
    await db_session.commit()
    step = WorkflowStep(
        id=str(uuid4()), workflow_id=workflow.id, step_key="day3", step_type="followup_check_due",
        status="running", due_at=CREATED_AT + timedelta(days=3), run_after=CREATED_AT + timedelta(days=3),
        payload={"check": "day3"},
    )
    db_session.add(step)
    await db_session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx = StepContext(session=db_session, step=step, workflow=workflow, now=now, channel=get_channel())
    result = await followup_check_due(ctx)

    assert result.outcome == "succeeded"
    action = (await db_session.scalars(select(PendingAction).where(PendingAction.patient_id == patient.id))).one()
    assert action.draft_text == ""
    assert action.draft_source == "llm"
    assert action.action_type == "followup_day3"
    assert action.workflow_step_id == step.id


async def test_followup_check_due_superseded_when_plan_cancelled(db_session):
    patient = await _patient(db_session)
    clinician = await _clinician(db_session)
    plan = FollowupPlan(id=str(uuid4()), patient_id=patient.id, created_by_user_id=clinician.id, created_at=CREATED_AT, status="cancelled")
    db_session.add(plan)
    await db_session.commit()
    workflow = Workflow(id=str(uuid4()), definition_key="patient_followup", patient_id=patient.id, followup_plan_id=plan.id, status="active")
    db_session.add(workflow)
    await db_session.commit()
    step = WorkflowStep(
        id=str(uuid4()), workflow_id=workflow.id, step_key="day3", step_type="followup_check_due",
        status="running", due_at=CREATED_AT + timedelta(days=3), run_after=CREATED_AT + timedelta(days=3),
        payload={"check": "day3"},
    )
    db_session.add(step)
    await db_session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx = StepContext(session=db_session, step=step, workflow=workflow, now=now, channel=get_channel())
    result = await followup_check_due(ctx)

    assert result.outcome == "superseded"
    actions = (await db_session.scalars(select(PendingAction).where(PendingAction.patient_id == patient.id))).all()
    assert actions == []
