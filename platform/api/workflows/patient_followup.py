"""`patient_followup` -- the third real workflow definition (SPEC-014).
Day 3/7/30 checks. `enroll_plan()` is called directly from
`POST /api/followups` (the clinician creating a `FollowupPlan` IS the
approval of the *schedule* -- not event-driven like the other two
definitions, since there is no existing event for "a follow-up plan
was created" and inventing one solely to route back to the same
process would add nothing).

The step handler never calls the LLM (SPEC-009's "no LLM inside the
tick, ever") -- it creates an empty-draft `PendingAction` and stops.
The draft itself is generated on demand, only when a clinician opens
the approval queue, via `POST /api/approvals/{id}/draft`
(`platform/api/routers/approvals.py`) calling
`intelligence.mcp.patient_comms_server.draft_message` directly -- the
same split as `find_interactions`/`check_drug_interactions`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import FollowupPlan, PendingAction, Workflow, WorkflowStep

from .registry import StepContext, StepResult, StepTypeSpec, register_step_type

DEFINITION_KEY = "patient_followup"
STEP_TYPE = "followup_check_due"

CHECK_OFFSETS: Dict[str, timedelta] = {
    "day3": timedelta(days=3),
    "day7": timedelta(days=7),
    "day30": timedelta(days=30),
}

# A check fired more than this late has missed its clinical window
# entirely (a "day 3 check" delivered on day 12 is not a day-3 check) --
# unlike the alert/appointment definitions, this one does NOT catch up
# forever.
MAX_LATENESS = timedelta(days=2)

PENDING_ACTION_EXPIRES_AFTER = timedelta(days=14)


async def enroll_plan(session: AsyncSession, plan: FollowupPlan) -> Workflow:
    """Called directly from the router that creates `plan` -- not an
    event subscriber, see module docstring. Does not commit."""
    workflow = Workflow(
        id=str(uuid4()),
        definition_key=DEFINITION_KEY,
        patient_id=plan.patient_id,
        followup_plan_id=plan.id,
        status="active",
        context={"instructions": plan.instructions},
    )
    session.add(workflow)

    for step_key, offset in CHECK_OFFSETS.items():
        due_at = plan.created_at + offset
        session.add(
            WorkflowStep(
                id=str(uuid4()),
                workflow_id=workflow.id,
                step_key=step_key,
                step_type=STEP_TYPE,
                status="pending",
                due_at=due_at,
                run_after=due_at,
                max_lateness_seconds=int(MAX_LATENESS.total_seconds()),
                payload={"check": step_key},
            )
        )
    return workflow


async def followup_check_due(ctx: StepContext) -> StepResult:
    plan = await ctx.session.get(FollowupPlan, ctx.workflow.followup_plan_id)
    if plan is None or plan.status != "active":
        return StepResult(outcome="superseded", detail="plan no longer active")

    check_name = ctx.step.payload.get("check", ctx.step.step_key)
    action = PendingAction(
        id=str(uuid4()),
        workflow_step_id=ctx.step.id,
        patient_id=plan.patient_id,
        action_type=f"followup_{check_name}",
        draft_text="",
        draft_source="llm",
        proposed_payload={
            "followup_plan_id": plan.id,
            "check": check_name,
            "instructions": plan.instructions,
        },
        expires_at=ctx.now + PENDING_ACTION_EXPIRES_AFTER,
    )
    ctx.session.add(action)

    return StepResult(outcome="succeeded", data={"pending_action_id": action.id})


register_step_type(
    StepTypeSpec(
        step_type=STEP_TYPE,
        handler=followup_check_due,
        max_attempts=3,
        max_lateness_seconds=int(MAX_LATENESS.total_seconds()),
        timeout_seconds=10.0,
        reads_phi=True,
    )
)

__all__ = ["DEFINITION_KEY", "STEP_TYPE", "CHECK_OFFSETS", "enroll_plan", "followup_check_due"]
