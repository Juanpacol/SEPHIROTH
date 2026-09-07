"""Workflow instantiation. Phase 7 ships exactly one caller --
`seed_alert_refresh_workflows` -- since appointment/consultation/alert
triggers (Phase 10+) don't exist yet. Kept as its own module so later
phases' `start_workflow(session, definition_key, ...)` general-purpose
entry point lands here without disturbing `engine.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Patient, Workflow, WorkflowStep

from .registry import STEP_TYPES


async def cancel_workflow(session: AsyncSession, workflow: Workflow, now: datetime) -> None:
    """Cancels a `Workflow` and every one of its still-pending/running
    steps -- shared by Phase 9's alert resolution and Phase 10's
    appointment cancellation, both of which need "the thing this
    workflow exists to act on no longer needs acting on" to stop the
    tick from ever touching it again. Does not commit -- caller's
    transaction, same discipline as everything else in this package."""
    workflow.status = "cancelled"
    workflow.completed_at = now
    pending_steps = (
        await session.scalars(
            select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow.id, WorkflowStep.status.in_(("pending", "running"))
            )
        )
    ).all()
    for step in pending_steps:
        step.status = "cancelled"


async def seed_alert_refresh_workflows(session: AsyncSession) -> int:
    """Ensures every patient has exactly one active `alert_refresh`
    workflow with one due-now step. Idempotent: a patient that already
    has an active `alert_refresh` workflow is skipped. Returns the
    number of workflows created. Not run automatically -- called by hand
    or a one-off script, same convention as `real_data/`'s fetch/import
    scripts."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    spec = STEP_TYPES["alert_refresh"]

    existing_patient_ids = {
        row
        for row in (
            await session.scalars(
                select(Workflow.patient_id).where(
                    Workflow.definition_key == "alert_refresh", Workflow.status == "active"
                )
            )
        ).all()
    }

    patients = (await session.scalars(select(Patient))).all()
    created = 0
    for patient in patients:
        if patient.id in existing_patient_ids:
            continue
        workflow = Workflow(
            id=str(uuid4()),
            definition_key="alert_refresh",
            patient_id=patient.id,
            status="active",
            context={},
        )
        session.add(workflow)
        session.add(
            WorkflowStep(
                id=str(uuid4()),
                workflow_id=workflow.id,
                step_key="refresh",
                step_type="alert_refresh",
                status="pending",
                due_at=now,
                run_after=now,
                max_lateness_seconds=spec.max_lateness_seconds,
                max_attempts=spec.max_attempts,
            )
        )
        created += 1

    if created:
        await session.commit()
    return created


__all__ = ["seed_alert_refresh_workflows", "cancel_workflow"]
