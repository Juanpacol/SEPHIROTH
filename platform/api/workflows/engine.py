"""The tick engine -- the only module in this package containing SQL for
claiming/executing workflow steps. See SPEC-009 for the full algorithm
and its rationale (status-CAS + lease over `FOR UPDATE SKIP LOCKED`, so
SQLite and Postgres run the identical claim path).

Every datetime here is naive UTC, matching the rest of the schema --
`func.now()` is never used in a predicate (Postgres would return it
timezone-aware); the caller's own `datetime.now(timezone.utc).replace(tzinfo=None)`
is passed explicitly instead.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Dict, List

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import add_phi_access
from core.config import settings
from core.db import SYSTEM_WORKFLOW_USER_ID
from data.schemas import Workflow, WorkflowStep
from sephiroth.contracts.enums import RecoveryActionType
from sephiroth.workflows.events import dispatch_pending
from sephiroth.workflows.policy import classify_step_failure, decide_step_recovery, is_stale, next_run_after

from . import definitions  # noqa: F401 -- import-time side effect: populates registry.STEP_TYPES
from .channels import get_channel
from .registry import STEP_TYPES, StepContext

logger = logging.getLogger(__name__)


@dataclass
class TickSummary:
    tick_id: str
    claimed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    remaining: int = 0
    deferred: int = 0
    events_dispatched: int = 0
    # Task upkeep (SPEC-018). Counted but deliberately absent from to_dict():
    # the tick's HTTP response shape is what an external cron consumes, and
    # SPEC-009 §6.5 fixed it.
    tasks_reopened: int = 0
    tasks_superseded: int = 0
    tasks_created: int = 0
    no_shows: int = 0
    #: Push deliveries attempted this tick. Absent from `to_dict()` for the
    #: same reason the counters above are: the cron response shape is frozen.
    push_sent: int = 0
    push_failed: int = 0
    # Not included in to_dict() -- the HTTP response shape to the cron
    # caller never changes. Only read by internal.py to compose an
    # ops_notify.py Slack payload (workflow_id/step_id only, never
    # patient_id -- see that module's docstring).
    failed_steps: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "tick_id": self.tick_id,
            "claimed": self.claimed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "remaining": self.remaining,
            "events_dispatched": self.events_dispatched,
        }


async def reclaim_expired_leases(session: AsyncSession, now: datetime) -> int:
    """Crash recovery: a step left `running` past its lease is handed
    back to the pool. Runs once at the top of every tick."""
    result = await session.execute(
        update(WorkflowStep)
        .where(WorkflowStep.status == "running", WorkflowStep.lease_expires_at < now)
        .values(status="pending", claimed_by="")
    )
    await session.commit()
    return result.rowcount or 0


async def select_due_step_ids(session: AsyncSession, now: datetime, batch_size: int) -> list[str]:
    rows = await session.scalars(
        select(WorkflowStep.id)
        .where(WorkflowStep.status == "pending", WorkflowStep.run_after <= now)
        .order_by(WorkflowStep.run_after)
        .limit(batch_size)
    )
    return list(rows.all())


async def claim_step(
    session: AsyncSession, step_id: str, tick_id: str, now: datetime, lease_seconds: int
) -> bool:
    """Status-CAS claim. Returns True iff this call won the race."""
    result = await session.execute(
        update(WorkflowStep)
        .where(WorkflowStep.id == step_id, WorkflowStep.status == "pending")
        .values(
            status="running",
            attempts=WorkflowStep.attempts + 1,
            claimed_by=tick_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
    )
    await session.commit()
    return (result.rowcount or 0) == 1


#: A handler that asks to be reconsidered "now" would be re-claimed by the same
#: tick's remaining budget and spin. One minute is below the 5-minute cron
#: cadence, so it costs nothing real and bounds the pathological case.
MIN_DEFER_SECONDS = 60

#: Slack added on top of a deferral when `extend_lateness` is set, so a step
#: that wakes up exactly at the window's edge is not immediately stale.
DEFER_LATENESS_SLACK_SECONDS = 15 * 60


async def _defer_step(
    session: AsyncSession,
    step: WorkflowStep,
    spec: Any,
    result: Any,
    now: datetime,
) -> str:
    """Put a step back to sleep without charging it an attempt.

    A deferral is a decision, not a failure: the handler looked, decided now is
    the wrong moment, and said when to ask again. Consuming a retry for that
    would mean three quiet nights in a row permanently kill a reminder.
    """
    retry_at = result.retry_at or (now + timedelta(seconds=MIN_DEFER_SECONDS))
    retry_at = max(retry_at, now + timedelta(seconds=MIN_DEFER_SECONDS))

    step.status = "pending"
    step.run_after = retry_at
    # `claim_step` already incremented this on the way in. Handing the attempt
    # back is what makes "deferred is not an attempt" true rather than stated.
    step.attempts = max(step.attempts - 1, 0)
    step.deferred_count += 1
    step.last_error = ""

    if result.extend_lateness:
        needed = int((retry_at - step.due_at).total_seconds()) + DEFER_LATENESS_SLACK_SECONDS
        current = step.max_lateness_seconds
        if current is None or needed > current:
            step.max_lateness_seconds = needed

    if spec.max_defers is not None and step.deferred_count > spec.max_defers:
        # An unbounded defer loop is invisible: nothing errors, nothing sends.
        # Failing loudly is the only way anyone finds out.
        step.status = "failed"
        step.last_error = f"defer limit exceeded ({step.deferred_count} > {spec.max_defers})"
        logger.warning("workflow step %s exceeded its defer limit", step.id)
        await session.commit()
        return "failed"

    await session.commit()
    return "deferred"


async def execute_step(session: AsyncSession, step_id: str, now: datetime) -> str:
    """Runs one already-claimed step to a terminal-for-this-attempt state.
    Returns "succeeded" | "failed" | "skipped" | "superseded" | "deferred" |
    "error" (unknown step type, terminal immediately).

    "deferred" is the one outcome that is not terminal even for this attempt:
    the step goes back to `pending` with its attempt handed back."""
    step = await session.get(WorkflowStep, step_id)
    if step is None:
        return "error"
    workflow = await session.get(Workflow, step.workflow_id)
    if workflow is None:
        step.status = "failed"
        step.last_error = "parent workflow not found"
        await session.commit()
        return "failed"

    spec = STEP_TYPES.get(step.step_type)
    if spec is None:
        step.status = "failed"
        step.last_error = f"unknown step_type: {step.step_type}"
        await session.commit()
        return "failed"

    # The per-row budget wins when set. `on_new_appointment` and `enroll_plan`
    # populate `WorkflowStep.max_lateness_seconds` per step and this code read
    # only the step *type*'s value, so that column was dead -- and a deferral
    # (below) needs to be able to widen one row's window without widening the
    # type's for every other step.
    lateness = (
        step.max_lateness_seconds if step.max_lateness_seconds is not None else spec.max_lateness_seconds
    )
    if is_stale(step.due_at, now, lateness):
        step.status = "skipped"
        step.last_error = ""
        await session.commit()
        return "skipped"

    if spec.reads_phi:
        # Committed immediately, before the handler runs -- PhiAccessLog is
        # append-only by design (its own docstring: "an audit trail that
        # could be edited by the audited party is not a trail"). Staging it
        # in the same transaction as the handler meant a handler exception
        # -> rollback() erased the audit row along with the failed attempt,
        # so a step that read PHI and then failed left no record it ever
        # happened. The read already occurred by this point regardless of
        # what the handler does next, so the record must survive on its own.
        add_phi_access(
            session, SYSTEM_WORKFLOW_USER_ID, workflow.patient_id, f"tick:{step.step_type}", "SYSTEM"
        )
        await session.commit()

    ctx = StepContext(session=session, step=step, workflow=workflow, now=now, channel=get_channel())
    try:
        result = await asyncio.wait_for(spec.handler(ctx), timeout=spec.timeout_seconds)
    except Exception as exc:  # noqa: BLE001 -- classified below, never re-raised past this point
        await session.rollback()
        step = await session.get(WorkflowStep, step_id)  # re-attach after rollback
        if step is None:
            # Deleted concurrently between claim and rollback -- nothing
            # left to mark failed. Availability-only: this tick's batch
            # would otherwise abort via an AttributeError below, leaving
            # already-claimed steps stuck `running` until lease expiry.
            logger.warning("workflow step %s vanished mid-execution; skipping", step_id)
            return "failed"
        failure = classify_step_failure(exc)
        action = decide_step_recovery(step.attempts, step.max_attempts)
        step.failure_category = failure.category.value
        step.last_error = failure.detail
        if action == RecoveryActionType.RETRY:
            step.status = "pending"
            step.run_after = next_run_after(step.attempts, now)
            outcome = "failed"  # this attempt failed; step lives on
        else:
            step.status = "failed"
            outcome = "failed"
            # Terminal only: a step that retried and then succeeded is not work
            # for a person. This one is never going to do what it was for.
            from .failure_task import report_step_needs_attention

            await report_step_needs_attention(session, step, workflow, now)
        await session.commit()
        logger.warning("workflow step %s failed (attempt %d): %s", step_id, step.attempts, failure.detail)
        return outcome
    else:
        if result.outcome == "deferred":
            return await _defer_step(session, step, spec, result, now)

        step.status = result.outcome
        step.executed_at = now
        step.result = result.data
        step.last_error = ""
        remaining = await session.scalar(
            select(WorkflowStep.id).where(
                WorkflowStep.workflow_id == workflow.id,
                WorkflowStep.status.in_(("pending", "running")),
                WorkflowStep.id != step.id,
            )
        )
        if remaining is None:
            workflow.status = "completed"
            workflow.completed_at = now
        await session.commit()
        return result.outcome


async def run_tick(session: AsyncSession, tick_id: str) -> TickSummary:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    deadline = monotonic() + settings.workflow_tick_budget_seconds

    await reclaim_expired_leases(session, now)

    # Before the batch, so a no-show's cancelled workflow is not also processed
    # this tick, and so `MISSED_APPOINTMENT` is dispatched by the same tick that
    # produced it rather than waiting five minutes.
    from .instantiate import maybe_seed_alert_refresh
    from .no_show import sweep_missed_appointments
    from .push import dispatch_due

    summary_no_shows = await sweep_missed_appointments(session, now)
    await maybe_seed_alert_refresh(session)

    due_ids = await select_due_step_ids(session, now, settings.workflow_tick_batch_size)

    summary = TickSummary(tick_id=tick_id)
    summary.no_shows = summary_no_shows
    for step_id in due_ids:
        if monotonic() > deadline:
            break
        won = await claim_step(session, step_id, tick_id, now, settings.workflow_step_lease_seconds)
        if not won:
            continue
        summary.claimed += 1
        outcome = await execute_step(session, step_id, now)
        if outcome == "succeeded":
            summary.succeeded += 1
        elif outcome == "deferred":
            # Counted apart from skipped: a skip means the moment passed and the
            # work was dropped, a deferral means it is still coming. Reading
            # them as one number would hide a quiet-hours misconfiguration as
            # ordinary staleness.
            summary.deferred += 1
        elif outcome in ("skipped", "superseded"):
            summary.skipped += 1
        else:
            summary.failed += 1
            row = (
                await session.execute(
                    select(WorkflowStep.workflow_id, WorkflowStep.step_type).where(WorkflowStep.id == step_id)
                )
            ).first()
            if row is not None:
                summary.failed_steps.append(
                    {"step_id": step_id, "workflow_id": row.workflow_id, "step_type": row.step_type}
                )

    summary.remaining = (
        await session.scalar(
            select(func.count())
            .select_from(WorkflowStep)
            .where(WorkflowStep.status == "pending", WorkflowStep.run_after <= now)
        )
        or 0
    )
    summary.events_dispatched = await dispatch_pending(session)

    # Task upkeep, after dispatch so a task created by this tick's events is
    # already visible to the reconciliation below.
    #
    # `reconcile_tasks` is not belt-and-braces for the service path: it is the
    # only thing that catches sources closed by a bulk UPDATE, which
    # `approvals.py::_expire_due_pending` performs by construction and which
    # therefore bypasses every Python hook.
    from ..services.task_adapters import reconcile_tasks
    from ..services.task_service import reopen_due_snoozed

    summary.tasks_reopened = await reopen_due_snoozed(session, now)
    summary.tasks_superseded = await reconcile_tasks(session, now)

    if settings.enable_task_inbox:
        # Behind the flag because this is the half that REPLACES the dashboard's
        # read-time derivation. The adapter-driven writes above are not gated:
        # the table has to be warm before anyone switches the inbox on, or the
        # first thing a clinician sees is an empty list described as "nothing
        # to do".
        from ..services.task_derivation import sync_derived_tasks

        derived = await sync_derived_tasks(session, now)
        summary.tasks_created = derived["created"]
        summary.tasks_superseded += derived["superseded"]

    # Last, and after the commit-worthy work above: a push service having a bad
    # afternoon must not stop appointments being reminded. `dispatch_due`
    # catches every failure itself; this guard is for the one it cannot.
    try:
        summary.push_sent, summary.push_failed = await dispatch_due(session, now)
    except Exception:  # pragma: no cover - defensive
        logger.exception("push dispatch failed; the rest of the tick stands")

    await session.commit()
    return summary


__all__ = [
    "TickSummary",
    "reclaim_expired_leases",
    "select_due_step_ids",
    "claim_step",
    "execute_step",
    "run_tick",
]
