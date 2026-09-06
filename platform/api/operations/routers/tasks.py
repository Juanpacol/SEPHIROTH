"""The clinical task inbox (SPEC-018).

One verb per transition rather than a single `PATCH {status}`. The guards
differ per transition — snoozing checks a cap and a severity, dismissing needs
a reason, claiming checks who holds it — and a generic PATCH hides all of that
behind a field assignment, which is how a state machine quietly stops being
one. It is the same reasoning that gave `alerts.py` `review` and `resolve`
instead of a status field.

This is the first paginated endpoint in the codebase. Offset paging, not a
keyset cursor: the default order is (severity, due date), which is not
monotonic, so a cursor would be fragile for no gain at the depth an inbox is
actually read to.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import add_phi_access
from api.services import task_service as svc
from api.services.task_adapters import can_complete, complete_task
from api.services.task_adapters import reopen_task as _reopen_with_source
from api.timeparse import require_aware
from auth.deps import require_clinician
from core.db import get_session
from data.schemas import Patient, Task, User

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _task_out(task: Task, *, patient_name: Optional[str] = None) -> Dict[str, Any]:
    completable, refusal = can_complete(task)
    return {
        "id": task.id,
        "source": {"kind": task.source_type, "id": task.source_id},
        "category": task.category,
        "severity": task.severity,
        "status": task.status,
        "title": task.title,
        "detail": task.detail,
        "context": task.context,
        "patient_id": task.patient_id,
        "patient_name": patient_name,
        "assigned_to_user_id": task.assigned_to_user_id,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "snoozed_until": task.snoozed_until.isoformat() if task.snoozed_until else None,
        "escalation_level": task.escalation_level,
        "dismiss_reason": task.dismiss_reason,
        "closed_at": task.closed_at.isoformat() if task.closed_at else None,
        "created_at": task.created_at.isoformat(),
        # The inbox needs to know *before* offering the button that this task
        # cannot be completed from here, so the refusal is not a surprise 409.
        "completable": completable,
        "completable_refusal": refusal,
    }


async def _patient_names(session: AsyncSession, tasks: List[Task]) -> Dict[str, str]:
    ids = {t.patient_id for t in tasks if t.patient_id}
    if not ids:
        return {}
    from sqlalchemy import select

    rows = (await session.execute(select(Patient.id, Patient.name).where(Patient.id.in_(ids)))).all()
    return {pid: name for pid, name in rows}


def _audit(session: AsyncSession, actor: User, tasks: List[Task], route: str, method: str) -> None:
    """One row per distinct patient whose chart this read exposed.

    A task carries the patient's name and a clinical title, so listing tasks
    is a PHI read even though it never opens a chart — the same reason
    `patients.py` logs its list endpoint.
    """
    for patient_id in {t.patient_id for t in tasks if t.patient_id}:
        add_phi_access(session, actor.id, patient_id, route, method)


@router.get("", summary="The task inbox, filtered and paginated")
async def list_tasks(
    status: List[str] = Query(default=["open", "in_progress", "snoozed"]),
    category: Optional[str] = None,
    severity: Optional[str] = None,
    source_type: Optional[str] = None,
    patient_id: Optional[str] = None,
    assignee: Optional[str] = Query(None, description="me | unassigned | a user id"),
    overdue: bool = False,
    q: Optional[str] = None,
    sort: str = Query("priority", pattern="^(priority|due|created)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    page = await svc.list_tasks(
        session,
        svc.TaskFilters(
            statuses=status,
            category=category,
            severity=severity,
            source_type=source_type,
            patient_id=patient_id,
            assignee=assignee,
            actor_user_id=clinician.id,
            overdue=overdue,
            query=q,
            sort=sort,
            limit=limit,
            offset=offset,
        ),
    )
    names = await _patient_names(session, page.items)
    _audit(session, clinician, page.items, "/api/tasks", "GET")
    await session.commit()
    return {
        "items": [_task_out(t, patient_name=names.get(t.patient_id or "")) for t in page.items],
        "total_count": page.total_count,
        "limit": page.limit,
        "offset": page.offset,
        "has_more": page.has_more,
    }


@router.get("/count", summary="Inbox counters for the navigation badge")
async def task_counts(
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, int]:
    from sqlalchemy import func, select

    rows = (
        await session.execute(
            select(Task.status, func.count()).where(Task.status.in_(svc.OPEN_STATUSES)).group_by(Task.status)
        )
    ).all()
    by_status = {status: int(count) for status, count in rows}

    mine = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status.in_(svc.OPEN_STATUSES), Task.assigned_to_user_id == clinician.id)
        )
        or 0
    )
    unassigned = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status.in_(svc.OPEN_STATUSES), Task.assigned_to_user_id.is_(None))
        )
        or 0
    )
    overdue = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.status.in_(svc.OPEN_STATUSES),
                Task.due_at.is_not(None),
                Task.due_at < _now(),
            )
        )
        or 0
    )
    return {
        # `open` is the *status*, not the sum: the three open statuses are
        # reported alongside it, so summing them into a field named after one
        # of them made "open + in_progress" count the same task twice for any
        # caller that added the fields up. `total_open` is the sum, named as
        # one.
        "open": by_status.get("open", 0),
        "in_progress": by_status.get("in_progress", 0),
        "snoozed": by_status.get("snoozed", 0),
        "total_open": sum(by_status.values()),
        "mine": mine,
        "unassigned": unassigned,
        "overdue": overdue,
    }


async def _get_task(session: AsyncSession, task_id: str) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}", summary="One task with its full history")
async def get_task(
    task_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    task = await _get_task(session, task_id)
    names = await _patient_names(session, [task])
    events = await svc.task_events(session, task.id)
    _audit(session, clinician, [task], f"/api/tasks/{task_id}", "GET")
    await session.commit()
    return {
        **_task_out(task, patient_name=names.get(task.patient_id or "")),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "actor_user_id": e.actor_user_id,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "note": e.note,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }


class AssignBody(BaseModel):
    assignee_id: str


class SnoozeBody(BaseModel):
    until: datetime


class DismissBody(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


async def _apply(
    session: AsyncSession,
    task: Task,
    action: str,
    clinician: User,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Every transition route funnels through here so the 409 mapping and the
    commit happen in exactly one place."""
    try:
        await svc.transition(session, task, action, actor=clinician, now=_now(), **kwargs)
    except svc.TaskTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _task_out(task)


@router.post("/{task_id}/claim")
async def claim_task(
    task_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    return await _apply(session, await _get_task(session, task_id), "claim", clinician)


@router.post("/{task_id}/assign")
async def assign_task(
    task_id: str,
    body: AssignBody,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    return await _apply(
        session, await _get_task(session, task_id), "assign", clinician, assignee_id=body.assignee_id
    )


@router.post("/{task_id}/snooze")
async def snooze_task(
    task_id: str,
    body: SnoozeBody,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    # A snooze that ends early is the one thing a snooze must not do, and a
    # naive value read as the server's clock ends five hours early on the
    # on-premise deployment. It used to be trusted as UTC here; it is now
    # refused, which is the same contract every other datetime field keeps
    # (SPEC-027 B-1).
    until = require_aware(body.until, "until")
    return await _apply(session, await _get_task(session, task_id), "snooze", clinician, snooze_until=until)


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    return await _apply(session, await _get_task(session, task_id), "resume", clinician)


@router.post("/{task_id}/complete")
async def complete(
    task_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Completing also applies the consequence to the task's source — an alert
    task resolves its alert. Some sources refuse: closing an approval row is
    not the same act as consenting to send the message it holds."""
    task = await _get_task(session, task_id)
    try:
        await complete_task(session, task, actor=clinician, now=_now())
    except svc.TaskTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _task_out(task)


@router.post("/{task_id}/dismiss")
async def dismiss_task(
    task_id: str,
    body: DismissBody,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    return await _apply(session, await _get_task(session, task_id), "dismiss", clinician, reason=body.reason)


@router.post("/{task_id}/reopen")
async def reopen_task(
    task_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Reopening also undoes what completing did to the source — a reopened
    alert task un-resolves its alert. Otherwise the undo is cosmetic: the task
    returns, the alert stays resolved, and the next reconciliation sweep
    supersedes the task again because its source is still terminal."""
    task = await _get_task(session, task_id)
    try:
        await _reopen_with_source(session, task, actor=clinician, now=_now())
    except svc.TaskTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _task_out(task)


@router.post("/{task_id}/comment")
async def comment_on_task(
    task_id: str,
    body: CommentBody,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    task = await _get_task(session, task_id)
    try:
        await svc.comment(session, task, actor=clinician, body=body.body)
    except svc.TaskTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _task_out(task)


__all__ = ["router"]
