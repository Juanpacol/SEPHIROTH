"""Turning things that happen into tasks, and keeping the two in step.

A task is a view of work whose authority lives elsewhere: an `Alert`, a
`PendingAction`, a `FollowupPlan`, a `WorkflowStep` that gave up. Each adapter
here owns three questions for one source type:

- what task does this source produce, and under what `dedupe_key`
- may a clinician close the task directly, or must the source close first
- what happens to the source when the task is completed

The middle question is the one that matters clinically. Completing an *alert*
task is a real clinical act, so it resolves the alert. Completing an *approval*
task is not: approving a message to a patient is consent, and consent is given
by pressing approve on the message, not by tidying an inbox row. That adapter
refuses, and the task closes when the approval does.

Consistency in the other direction is a plain function call rather than an
event subscriber. The outbox only dispatches on the 5-minute tick, and a
clinician who resolves an alert has to watch its task disappear now, not
eventually.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Alert, FollowupPlan, PendingAction, Task, User, Workflow

from . import task_service as svc


class SourceAdapter(Protocol):
    source_type: str

    async def on_task_completed(
        self, session: AsyncSession, task: Task, actor: User, now: datetime
    ) -> None: ...

    def can_complete(self, task: Task) -> tuple[bool, str]: ...

    async def is_stale(self, session: AsyncSession, task: Task) -> bool: ...


@dataclass(frozen=True)
class _Adapter:
    source_type: str
    #: (session, task) -> the source row, or None when it is gone.
    load: Callable[[AsyncSession, Task], Any]
    #: Statuses of the source that mean the task has nothing left to represent.
    terminal_source_statuses: frozenset
    #: When False, completing the task is refused with `refusal`.
    completable: bool = True
    refusal: str = ""
    #: Applied to the source row when the task is completed.
    on_complete: Optional[Callable[..., Any]] = None


async def _load_alert(session: AsyncSession, task: Task) -> Optional[Alert]:
    return await session.get(Alert, task.source_id) if task.source_id else None


async def _load_pending_action(session: AsyncSession, task: Task) -> Optional[PendingAction]:
    return await session.get(PendingAction, task.source_id) if task.source_id else None


async def _load_followup(session: AsyncSession, task: Task) -> Optional[FollowupPlan]:
    return await session.get(FollowupPlan, task.source_id) if task.source_id else None


async def _resolve_alert(session: AsyncSession, alert: Alert, actor: User, now: datetime) -> None:
    """The body of `/api/alerts/{id}/resolve`, minus the HTTP.

    It moved here so completing the task and resolving the alert are the same
    code, not two implementations that agree until one is edited. Review is
    stamped if it is missing, because completing the task *is* the review —
    `dashboard.py::_dashboard_alerts` computes its response-time metric from
    `reviewed_at`, and a resolved alert with no review time leaves that
    metric's numerator empty.
    """
    from ..workflows.instantiate import cancel_workflow

    if alert.reviewed_at is None:
        alert.reviewed_at = now
        alert.reviewed_by = actor.id
    alert.status = "resolved"
    alert.resolved_at = now

    workflows = (
        await session.scalars(
            select(Workflow).where(Workflow.alert_id == alert.id, Workflow.status == "active")
        )
    ).all()
    for wf in workflows:
        await cancel_workflow(session, wf, now)


ADAPTERS: Dict[str, _Adapter] = {
    "alert": _Adapter(
        source_type="alert",
        load=_load_alert,
        terminal_source_statuses=frozenset({"resolved"}),
        on_complete=_resolve_alert,
    ),
    "approval": _Adapter(
        source_type="approval",
        load=_load_pending_action,
        terminal_source_statuses=frozenset({"approved", "rejected", "expired"}),
        completable=False,
        refusal="approve or reject the message itself — closing this row is not consent",
    ),
    "followup": _Adapter(
        source_type="followup",
        load=_load_followup,
        terminal_source_statuses=frozenset({"cancelled", "completed"}),
        completable=False,
        refusal="resolve the follow-up's pending message instead",
    ),
    # Sources with no lifecycle of their own: the task IS the record of the
    # work, so completing it needs nothing done to anything else. They still
    # appear here so `reconcile_tasks` knows they are legitimate.
    "automation": _Adapter(
        source_type="automation", load=lambda s, t: None, terminal_source_statuses=frozenset()
    ),
    "result": _Adapter(source_type="result", load=lambda s, t: None, terminal_source_statuses=frozenset()),
    "appointment": _Adapter(
        source_type="appointment", load=lambda s, t: None, terminal_source_statuses=frozenset()
    ),
    "deteriorating": _Adapter(
        source_type="deteriorating", load=lambda s, t: None, terminal_source_statuses=frozenset()
    ),
    "interaction": _Adapter(
        source_type="interaction", load=lambda s, t: None, terminal_source_statuses=frozenset()
    ),
}


def can_complete(task: Task) -> tuple[bool, str]:
    adapter = ADAPTERS.get(task.source_type)
    if adapter is None:
        return True, ""
    return adapter.completable, adapter.refusal


async def complete_task(
    session: AsyncSession, task: Task, *, actor: User, now: Optional[datetime] = None
) -> Task:
    """Complete a task and apply the consequence to its source.

    Raises `TaskTransitionError` when the source says a clinician may not close
    the work from here — see the module docstring for why an approval does.
    """
    allowed, refusal = can_complete(task)
    if not allowed:
        raise svc.TaskTransitionError(refusal)

    moment = now or datetime.utcnow()
    adapter = ADAPTERS.get(task.source_type)
    if adapter is not None and adapter.on_complete is not None:
        source = await adapter.load(session, task)
        if source is not None:
            await adapter.on_complete(session, source, actor, moment)

    return await svc.transition(session, task, "complete", actor=actor, now=moment)


async def reconcile_tasks(session: AsyncSession, now: Optional[datetime] = None, limit: int = 200) -> int:
    """Supersede tasks whose source is gone or finished. Runs from the tick.

    This is not belt-and-braces for the call-a-service path — it is required.
    `approvals.py::_expire_due_pending` expires overdue approvals with a bulk
    UPDATE, which bypasses every Python hook by construction. Without this
    sweep those tasks would sit open forever, pointing at a row that has
    nothing left to decide.

    The window between such a write and the next tick is the drift this design
    accepts: up to one tick, a task can name work that no longer exists.
    """
    moment = now or datetime.utcnow()
    tasks = (
        await session.scalars(
            select(Task)
            .where(Task.status.in_(svc.OPEN_STATUSES), Task.source_id.is_not(None))
            .order_by(Task.updated_at.asc())
            .limit(limit)
        )
    ).all()

    superseded = 0
    for task in tasks:
        adapter = ADAPTERS.get(task.source_type)
        if adapter is None or not adapter.terminal_source_statuses:
            continue
        source = await adapter.load(session, task)
        gone = source is None
        finished = source is not None and getattr(source, "status", None) in adapter.terminal_source_statuses
        if gone or finished:
            await svc.transition(
                session,
                task,
                "supersede",
                actor=None,
                now=moment,
                note="source row is gone" if gone else "source reached a terminal state",
            )
            superseded += 1
    return superseded


__all__ = ["ADAPTERS", "can_complete", "complete_task", "reconcile_tasks"]
