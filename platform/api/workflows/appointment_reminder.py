"""`appointment_reminder` -- the second real workflow definition
(SPEC-012). Subscribes to `NEW_APPOINTMENT` (Phase 8) and enrolls two
steps: a T-24h reminder (fixed template, autonomous per the locked
"deterministic decides, LLM only drafts" rule) and a T-2h unconfirmed
check that escalates via a plain `Alert` -- reusing Phase 9's
`alert_escalation` pipeline rather than inventing a second notification
path, since an unresolved "patient hasn't confirmed" alert deserves the
exact same escalate-if-nobody-responds behavior a clinical alert does.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Alert, Appointment, User, Workflow, WorkflowStep
from sephiroth.workflows.events import WorkflowEvent

from .registry import StepContext, StepResult, StepTypeSpec, register_step_type

DEFINITION_KEY = "appointment_reminder"
REMINDER_STEP_TYPE = "appointment_reminder_t24"
UNCONFIRMED_STEP_TYPE = "appointment_unconfirmed_check"

REMINDER_LEAD_TIME = timedelta(hours=24)
REMINDER_MAX_LATENESS = timedelta(hours=6)
UNCONFIRMED_LEAD_TIME = timedelta(hours=2)


async def on_new_appointment(session: AsyncSession, event: WorkflowEvent) -> None:
    """Subscriber for `NEW_APPOINTMENT`. Enrolls one workflow with the
    two steps above, both anchored off `appt.start_at` at enrollment
    time -- a later reschedule is handled by each step's own handler
    re-checking `start_at` against the workflow's snapshot, not by
    rewriting `due_at` here."""
    appt = await session.get(Appointment, event.entity_id)
    if appt is None or appt.status != "booked":
        return

    existing = await session.scalar(
        select(Workflow).where(Workflow.appointment_id == appt.id, Workflow.status == "active")
    )
    if existing is not None:
        return  # idempotent: don't double-enroll the same appointment

    workflow = Workflow(
        id=str(uuid4()),
        definition_key=DEFINITION_KEY,
        patient_id=appt.patient_id,
        appointment_id=appt.id,
        status="active",
        context={"start_at": appt.start_at.isoformat()},
    )
    session.add(workflow)

    reminder_due = appt.start_at - REMINDER_LEAD_TIME
    session.add(
        WorkflowStep(
            id=str(uuid4()),
            workflow_id=workflow.id,
            step_key="reminder_t24",
            step_type=REMINDER_STEP_TYPE,
            status="pending",
            due_at=reminder_due,
            run_after=reminder_due,
            max_lateness_seconds=int(REMINDER_MAX_LATENESS.total_seconds()),
        )
    )

    unconfirmed_due = appt.start_at - UNCONFIRMED_LEAD_TIME
    session.add(
        WorkflowStep(
            id=str(uuid4()),
            workflow_id=workflow.id,
            step_key="unconfirmed_check",
            step_type=UNCONFIRMED_STEP_TYPE,
            status="pending",
            due_at=unconfirmed_due,
            run_after=unconfirmed_due,
            max_lateness_seconds=None,  # a missed T-2h check still matters right up to start_at
        )
    )


async def _load_live_appointment(ctx: StepContext) -> Optional[Appointment]:
    """Shared re-validation: the anchor snapshot
    (`workflow.context["start_at"]`) must still match the live row, or
    this step is stale relative to a reschedule that happened after
    enrollment."""
    appt = await ctx.session.get(Appointment, ctx.workflow.appointment_id)
    if appt is None or appt.status != "booked":
        return None
    if appt.start_at.isoformat() != ctx.workflow.context.get("start_at"):
        return None  # rescheduled since enrollment -- a fresh NEW_APPOINTMENT event re-enrolls
    return appt


async def send_reminder_t24(ctx: StepContext) -> StepResult:
    appt = await _load_live_appointment(ctx)
    if appt is None:
        return StepResult(outcome="superseded", detail="appointment cancelled or rescheduled")

    patient_login = await ctx.session.scalar(select(User).where(User.patient_id == appt.patient_id, User.is_active.is_(True)))
    if patient_login is None:
        return StepResult(outcome="skipped", detail="patient has no portal login")

    when = appt.start_at.strftime("%A, %B %-d at %H:%M UTC") if hasattr(appt.start_at, "strftime") else str(appt.start_at)
    sent = await ctx.channel.send(
        ctx.session,
        patient_login.id,
        "appointment_reminder",
        f"Reminder: you have an appointment on {when}.",
        dedupe_key=f"step:{ctx.step.id}:{patient_login.id}",
        related_appointment_id=appt.id,
    )
    return StepResult(outcome="succeeded", data={"notified": sent})


async def escalate_if_unconfirmed(ctx: StepContext) -> StepResult:
    appt = await _load_live_appointment(ctx)
    if appt is None:
        return StepResult(outcome="superseded", detail="appointment cancelled or rescheduled")
    if appt.confirmed_at is not None:
        return StepResult(outcome="superseded", detail="patient already confirmed")

    existing = await ctx.session.scalar(
        select(Alert).where(
            Alert.category == "clinical", Alert.status == "active", Alert.source == "appointment_engine",
            Alert.patient_id == appt.patient_id,
        )
    )
    if existing is not None:
        return StepResult(outcome="succeeded", detail="already alerted", data={"alert_id": existing.id})

    alert = Alert(
        id=str(uuid4()),
        patient_id=appt.patient_id,
        category="clinical",
        severity="medium",
        title="Unconfirmed appointment",
        detail=f"Appointment at {appt.start_at.isoformat()} has not been confirmed by the patient.",
        source="appointment_engine",
    )
    ctx.session.add(alert)

    from sephiroth.workflows.events import CLINICAL_ALERT, emit

    emit(ctx.session, CLINICAL_ALERT, "alert", alert.id, patient_id=appt.patient_id)

    return StepResult(outcome="succeeded", data={"alert_id": alert.id})


register_step_type(
    StepTypeSpec(
        step_type=REMINDER_STEP_TYPE,
        handler=send_reminder_t24,
        max_attempts=3,
        max_lateness_seconds=int(REMINDER_MAX_LATENESS.total_seconds()),
        timeout_seconds=10.0,
        reads_phi=True,
    )
)
register_step_type(
    StepTypeSpec(
        step_type=UNCONFIRMED_STEP_TYPE,
        handler=escalate_if_unconfirmed,
        max_attempts=3,
        max_lateness_seconds=None,  # a missed check still matters right up to start_at
        timeout_seconds=10.0,
        reads_phi=True,
    )
)

__all__ = [
    "DEFINITION_KEY",
    "REMINDER_STEP_TYPE",
    "UNCONFIRMED_STEP_TYPE",
    "on_new_appointment",
    "send_reminder_t24",
    "escalate_if_unconfirmed",
]
