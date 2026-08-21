"""`alert_escalation` -- the first real workflow definition (SPEC-011).
One event subscriber (`on_clinical_alert`) + one step handler
(`escalate_if_unresolved`); no LLM, no patient-facing text, so it needs
neither the drafting tool nor the approval gate later phases add.

Escalation window is a fixed table by severity, not a policy engine --
there is exactly one tier (notify every active clinician once, then
stop) and one rule input (severity), so a table is the whole "policy"
that exists today. A real multi-tier escalation ladder is future work,
not something to half-build now.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Alert, User, Workflow, WorkflowStep
from sephiroth.workflows.events import CLINICAL_ALERT, WorkflowEvent

from .registry import StepContext, StepResult

DEFINITION_KEY = "alert_escalation"
STEP_TYPE = "alert_escalate_check"

ESCALATION_WINDOW_BY_SEVERITY: Dict[str, timedelta] = {
    "critical": timedelta(hours=1),
    "high": timedelta(hours=4),
    "medium": timedelta(hours=24),
    "low": timedelta(hours=72),
}


async def on_clinical_alert(session: AsyncSession, event: WorkflowEvent) -> None:
    """Subscriber for `CLINICAL_ALERT` (registered in
    `subscriptions.py`). Creates one `Workflow` anchored to the alert
    with a single due-dated `alert_escalate_check` step."""
    alert = await session.get(Alert, event.entity_id)
    if alert is None or alert.status != "active":
        return  # already handled between emit and dispatch -- nothing to escalate

    existing = await session.scalar(
        select(Workflow).where(Workflow.alert_id == alert.id, Workflow.status == "active")
    )
    if existing is not None:
        return  # idempotent: don't double-enroll the same alert

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window = ESCALATION_WINDOW_BY_SEVERITY.get(alert.severity, timedelta(hours=24))
    due_at = now + window

    workflow = Workflow(
        id=str(uuid4()),
        definition_key=DEFINITION_KEY,
        patient_id=alert.patient_id,
        alert_id=alert.id,
        status="active",
        context={"severity": alert.severity},
    )
    session.add(workflow)
    session.add(
        WorkflowStep(
            id=str(uuid4()),
            workflow_id=workflow.id,
            step_key="escalate_check",
            step_type=STEP_TYPE,
            status="pending",
            due_at=due_at,
            run_after=due_at,
            max_lateness_seconds=None,  # an overdue escalation still matters -- catch up forever
        )
    )


async def escalate_if_unresolved(ctx: StepContext) -> StepResult:
    """If the alert is still `active` when this fires, notify every
    active clinician and mark it escalated. If a clinician already
    reviewed/resolved it, this is a no-op -- `superseded`, matching the
    convention `appointment_reminder_t24` (Phase 10) will also use."""
    alert = await ctx.session.get(Alert, ctx.workflow.alert_id)
    if alert is None:
        return StepResult(outcome="superseded", detail="alert no longer exists")
    if alert.status != "active":
        return StepResult(outcome="superseded", detail=f"alert already {alert.status}")

    alert.escalated_at = ctx.now

    clinicians = (
        await ctx.session.scalars(select(User).where(User.role == "clinician", User.is_active.is_(True)))
    ).all()
    notified = 0
    for clinician in clinicians:
        sent = await ctx.channel.send(
            ctx.session,
            clinician.id,
            "alert_escalated",
            f"Unresolved alert escalated: {alert.title}",
            dedupe_key=f"step:{ctx.step.id}:{clinician.id}",
        )
        if sent:
            notified += 1

    return StepResult(outcome="succeeded", data={"notified": notified})


__all__ = [
    "DEFINITION_KEY",
    "STEP_TYPE",
    "ESCALATION_WINDOW_BY_SEVERITY",
    "on_clinical_alert",
    "escalate_if_unresolved",
]
