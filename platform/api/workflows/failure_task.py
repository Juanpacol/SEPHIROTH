"""A workflow step that gave up is somebody's problem.

`GET /api/dashboard/automation` counts failed steps, and a counter on a page
nobody has a reason to open is not how anyone finds out that a patient's
reminder never went. Filing it as a task puts it in the same inbox as every
other piece of outstanding work, which is the one place a clinician does look.

Deliberately not every failure: a step that retried and then succeeded is not
work for a person. Only terminal exhaustion reaches here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Workflow, WorkflowStep

logger = logging.getLogger(__name__)

#: Not `critical`: the automation failing is not itself a clinical emergency,
#: and marking it one would put it above real patient work in a shared inbox.
#: `high` because whatever it was going to do is now not going to happen.
SEVERITY = "high"


async def report_step_needs_attention(
    session: AsyncSession,
    step: WorkflowStep,
    workflow: Workflow,
    now: Optional[datetime] = None,
) -> None:
    """File a task for a step that exhausted its attempts. Never raises.

    Imported lazily by the engine and wrapped here, because a failure in the
    reporting of a failure must not take down the tick that is processing the
    rest of the batch.
    """
    try:
        from ..services import task_service

        await task_service.create_task(
            session,
            source_type="automation",
            source_id=step.id,
            category="automation",
            severity=SEVERITY,
            title=f"Automatización fallida: {step.step_type}",
            detail=step.last_error or "",
            patient_id=workflow.patient_id,
            # Keyed on the step, so a lease reclaim that re-runs and re-fails
            # the same row does not file the same problem twice.
            dedupe_key=f"automation:{step.id}",
            context={
                "step_type": step.step_type,
                "step_key": step.step_key,
                "workflow_id": workflow.id,
                "definition_key": workflow.definition_key,
                "attempts": step.attempts,
            },
            now=now,
        )
    except Exception:  # noqa: BLE001 -- reporting must never break the tick
        logger.exception("could not file a task for failed step %s", step.id)


__all__ = ["report_step_needs_attention", "SEVERITY"]
