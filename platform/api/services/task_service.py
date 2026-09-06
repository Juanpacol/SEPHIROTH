"""Creating, moving and closing clinical tasks (SPEC-018).

Everything that changes a `Task` goes through here, including the routes that
act on a task's *source* -- `/api/alerts/{id}/resolve` calls
`close_tasks_for_source` rather than leaving the task open behind it. That is
the whole point of the module: one implementation, reachable from both sides,
instead of two that agree until one of them is edited.

Transaction discipline: **nothing here commits.** See the package docstring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Task, TaskEvent, User

from .sla import due_at_for

# --------------------------------------------------------------------------
# The state machine
# --------------------------------------------------------------------------

OPEN_STATUSES = ("open", "in_progress", "snoozed")
TERMINAL_STATUSES = ("done", "dismissed", "superseded")

#: (from_status, action) -> to_status. Exported so tests assert against the
#: table itself rather than re-deriving it from a pile of if-statements, and so
#: the router never has to know which transitions exist.
TRANSITIONS: Dict[Tuple[str, str], str] = {
    ("open", "claim"): "in_progress",
    ("snoozed", "claim"): "in_progress",
    ("open", "assign"): "open",
    ("in_progress", "assign"): "in_progress",
    ("open", "snooze"): "snoozed",
    ("in_progress", "snooze"): "snoozed",
    ("snoozed", "resume"): "in_progress",
    ("open", "complete"): "done",
    ("in_progress", "complete"): "done",
    ("snoozed", "complete"): "done",
    ("open", "dismiss"): "dismissed",
    ("in_progress", "dismiss"): "dismissed",
    ("snoozed", "dismiss"): "dismissed",
    ("open", "escalate"): "open",
    ("in_progress", "escalate"): "in_progress",
    ("snoozed", "escalate"): "snoozed",
    ("open", "supersede"): "superseded",
    ("in_progress", "supersede"): "superseded",
    ("snoozed", "supersede"): "superseded",
    ("done", "reopen"): "open",
    ("dismissed", "reopen"): "open",
    # Deliberately absent: superseded -> anything. The work's reason to exist
    # is gone; resurrecting it would show a clinician something that no longer
    # refers to a real situation.
}

#: Only the system may perform these. A clinician "superseding" work would be a
#: dismissal with no reason recorded.
SYSTEM_ONLY_ACTIONS = frozenset({"supersede"})

#: action -> the `TaskEvent.event_type` it records. Spelled out rather than
#: derived from the action name: `ck_task_event_type` is a closed set, and
#: string surgery on the verb produces "dismissd" and "supersedd", which the
#: database rejects at write time rather than at review time.
EVENT_FOR_ACTION: Dict[str, str] = {
    "claim": "claimed",
    "assign": "assigned",
    "snooze": "snoozed",
    "resume": "resumed",
    "complete": "completed",
    "dismiss": "dismissed",
    "escalate": "escalated",
    "supersede": "superseded",
    "reopen": "reopened",
}

#: Same, for the source-driven close path, keyed by the status it lands on.
EVENT_FOR_STATUS: Dict[str, str] = {
    "done": "completed",
    "dismissed": "dismissed",
    "superseded": "superseded",
}

#: Never auto-close a critical task by snoozing it out of sight.
MAX_SNOOZE = timedelta(days=7)
REOPEN_WINDOW = timedelta(days=30)
MAX_ESCALATION_LEVEL = 2


class TaskTransitionError(ValueError):
    """A transition the state machine does not allow, or whose guard failed.

    The router maps this to 409. It is deliberately not an HTTPException:
    the tick calls these functions too, and it has no response to raise into.
    """


@dataclass
class TaskFilters:
    statuses: Sequence[str] = ()
    category: Optional[str] = None
    severity: Optional[str] = None
    source_type: Optional[str] = None
    patient_id: Optional[str] = None
    #: "me" | "unassigned" | a user id | None (any)
    assignee: Optional[str] = None
    actor_user_id: Optional[str] = None
    overdue: bool = False
    due_before: Optional[datetime] = None
    query: Optional[str] = None
    sort: str = "priority"
    limit: int = 50
    offset: int = 0


@dataclass
class TaskPage:
    items: List[Task] = field(default_factory=list)
    total_count: int = 0
    limit: int = 50
    offset: int = 0

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total_count


#: Worst first, regardless of which category a critical item happens to come
#: from. Mirrors `dashboard.py::_SEVERITY_RANK`, whose ordering the inbox
#: inherits so the two surfaces agree on what "most urgent" means.
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _now() -> datetime:
    """Naive UTC, matching every other datetime in this schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _record(
    session: AsyncSession,
    task: Task,
    event_type: str,
    *,
    actor: Optional[User],
    from_status: Optional[str] = None,
    to_status: Optional[str] = None,
    note: str = "",
    data: Optional[Dict[str, Any]] = None,
) -> TaskEvent:
    event = TaskEvent(
        task_id=task.id,
        event_type=event_type,
        actor_user_id=actor.id if actor is not None else None,
        from_status=from_status,
        to_status=to_status,
        note=note,
        data=data or {},
    )
    session.add(event)
    return event


# --------------------------------------------------------------------------
# Creation
# --------------------------------------------------------------------------


async def create_task(
    session: AsyncSession,
    *,
    source_type: str,
    category: str,
    severity: str,
    title: str,
    dedupe_key: str,
    source_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    detail: str = "",
    context: Optional[Dict[str, Any]] = None,
    due_at: Optional[datetime] = None,
    source_deadline: Optional[datetime] = None,
    assigned_to_user_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Tuple[Task, bool]:
    """Create the task unless `dedupe_key` already names one.

    Returns `(task, created)`. The second element matters to callers that
    should only notify on a genuinely new task -- re-deriving the same work on
    every tick must not produce a notification storm.

    A `superseded` task with this key is *not* revived: if the condition that
    retired it has genuinely returned, the caller's key should reflect the new
    occurrence. Silently reopening would resurrect work a clinician had
    already seen the end of.
    """
    existing = await session.scalar(select(Task).where(Task.dedupe_key == dedupe_key))
    if existing is not None:
        return existing, False

    moment = now or _now()
    task = Task(
        id=str(uuid4()),
        dedupe_key=dedupe_key,
        source_type=source_type,
        source_id=source_id,
        category=category,
        patient_id=patient_id,
        title=title,
        detail=detail,
        context=context or {},
        severity=severity,
        status="open",
        assigned_to_user_id=assigned_to_user_id,
        due_at=due_at or due_at_for(severity, moment, category=category, source_deadline=source_deadline),
        created_at=moment,
        updated_at=moment,
    )
    session.add(task)
    await session.flush()
    _record(session, task, "created", actor=None, to_status="open", data={"source_type": source_type})
    return task, True


# --------------------------------------------------------------------------
# Transitions
# --------------------------------------------------------------------------


async def transition(
    session: AsyncSession,
    task: Task,
    action: str,
    *,
    actor: Optional[User] = None,
    now: Optional[datetime] = None,
    assignee_id: Optional[str] = None,
    snooze_until: Optional[datetime] = None,
    reason: str = "",
    note: str = "",
) -> Task:
    """Apply `action` to `task`, or raise `TaskTransitionError`.

    `actor=None` means the system. Guards live here rather than in the router
    because the tick performs transitions too and would otherwise bypass them.
    """
    moment = now or _now()
    target = TRANSITIONS.get((task.status, action))
    if target is None:
        raise TaskTransitionError(f"cannot {action} a task that is {task.status}")

    if action in SYSTEM_ONLY_ACTIONS and actor is not None:
        raise TaskTransitionError(f"{action} is a system action")
    if action not in SYSTEM_ONLY_ACTIONS and action != "escalate" and actor is None:
        # A clinical decision needs a person against it; `ck_task_closed_requires_actor`
        # would refuse the write anyway, and failing here says why.
        raise TaskTransitionError(f"{action} requires a clinician")

    previous = task.status

    if action == "claim":
        # Claiming is the one transition two people race for, so the guard has
        # to live in the WHERE clause rather than in Python: a read-then-write
        # would let both requests read "unassigned" and both write themselves
        # in, and each clinician would walk away believing they own the work.
        # Same optimistic shape as `engine.py::claim_step`.
        claimed = await session.execute(
            update(Task)
            .where(
                Task.id == task.id,
                Task.status == previous,
                or_(Task.assigned_to_user_id.is_(None), Task.assigned_to_user_id == actor.id),
            )
            .values(
                status=target,
                assigned_to_user_id=actor.id,
                snoozed_until=None,
                updated_at=moment,
            )
        )
        if (claimed.rowcount or 0) != 1:
            raise TaskTransitionError("task is already claimed by someone else")
        # Bring the in-memory object in line with what the UPDATE actually did.
        await session.refresh(task)
        _record(
            session,
            task,
            EVENT_FOR_ACTION["claim"],
            actor=actor,
            from_status=previous,
            to_status=target,
        )
        return task

    elif action == "assign":
        if not assignee_id:
            raise TaskTransitionError("assign needs a target user")
        target_user = await session.get(User, assignee_id)
        if target_user is None or not getattr(target_user, "is_active", True):
            raise TaskTransitionError("assignee is not an active user")
        task.assigned_to_user_id = assignee_id

    elif action == "snooze":
        if snooze_until is None or snooze_until <= moment:
            raise TaskTransitionError("snooze needs a future time")
        if snooze_until > moment + MAX_SNOOZE:
            raise TaskTransitionError("snooze is capped at 7 days")
        if task.severity == "critical":
            raise TaskTransitionError("a critical task cannot be snoozed")
        task.snoozed_until = snooze_until

    elif action == "resume":
        task.snoozed_until = None

    elif action in ("complete", "dismiss"):
        if action == "dismiss" and not reason.strip():
            # Dismissing is closing clinical work without doing it; the reason
            # is the audit trail's only account of why.
            raise TaskTransitionError("dismiss needs a reason")
        task.closed_at = moment
        task.closed_by = actor.id if actor else None
        task.snoozed_until = None
        if action == "dismiss":
            task.dismiss_reason = reason.strip()[:300]

    elif action == "escalate":
        if task.escalation_level >= MAX_ESCALATION_LEVEL:
            raise TaskTransitionError("task is already at the highest escalation level")
        task.escalation_level += 1
        task.escalated_at = moment

    elif action == "supersede":
        task.closed_at = moment
        task.snoozed_until = None

    elif action == "reopen":
        if task.closed_at is not None and moment - task.closed_at > REOPEN_WINDOW:
            raise TaskTransitionError("reopen window has passed")
        task.closed_at = None
        task.closed_by = None
        task.dismiss_reason = ""

    task.status = target
    task.updated_at = moment
    _record(
        session,
        task,
        EVENT_FOR_ACTION[action],
        actor=actor,
        from_status=previous,
        to_status=target,
        note=note or reason,
        data={"assignee_id": assignee_id} if assignee_id else {},
    )
    return task


async def comment(session: AsyncSession, task: Task, *, actor: User, body: str) -> TaskEvent:
    if not body.strip():
        raise TaskTransitionError("a comment needs text")
    return _record(session, task, "commented", actor=actor, note=body.strip())


# --------------------------------------------------------------------------
# Keeping tasks and their sources in step
# --------------------------------------------------------------------------


async def close_tasks_for_source(
    session: AsyncSession,
    source_type: str,
    source_id: str,
    *,
    status: str = "done",
    actor: Optional[User] = None,
    reason: str = "",
    now: Optional[datetime] = None,
) -> int:
    """Close every open task pointing at this source row.

    Called from the *source's* own routes -- resolving an alert, approving a
    pending action -- so acting on the entity closes its task immediately
    rather than waiting for the next tick to notice.
    """
    moment = now or _now()
    tasks = (
        await session.scalars(
            select(Task).where(
                Task.source_type == source_type,
                Task.source_id == source_id,
                Task.status.in_(OPEN_STATUSES),
            )
        )
    ).all()

    for task in tasks:
        previous = task.status
        task.status = status
        task.closed_at = moment
        task.updated_at = moment
        task.snoozed_until = None
        if status == "done":
            # The database refuses a done task with no actor. When the source
            # closed itself without one (a bulk expiry), record it as
            # superseded instead -- which is the honest description anyway.
            if actor is None:
                task.status = "superseded"
            else:
                task.closed_by = actor.id
        elif status == "dismissed":
            task.closed_by = actor.id if actor is not None else None
            task.dismiss_reason = (reason or "closed by its source")[:300]
        _record(
            session,
            task,
            EVENT_FOR_STATUS[task.status],
            actor=actor,
            from_status=previous,
            to_status=task.status,
            note=reason,
        )
    return len(tasks)


async def reopen_due_snoozed(session: AsyncSession, now: Optional[datetime] = None) -> int:
    """Bring back tasks whose snooze has expired. Runs from the tick.

    A bulk UPDATE rather than a loop: this touches every snoozed task in the
    system on every tick, and it records no per-task event because "the snooze
    ran out" is not something a person did.
    """
    moment = now or _now()
    result = await session.execute(
        update(Task)
        .where(Task.status == "snoozed", Task.snoozed_until.is_not(None), Task.snoozed_until <= moment)
        .values(status="open", snoozed_until=None, updated_at=moment)
    )
    return result.rowcount or 0


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def _severity_order():
    """Order by severity without a database-specific CASE builder difference.

    SQLAlchemy's `case` with a value map renders on both SQLite and Postgres,
    which matters because the tests run on one and production on the other.
    """
    from sqlalchemy import case

    return case(SEVERITY_RANK, value=Task.severity, else_=99)


def _apply_filters(stmt: Select, filters: TaskFilters, now: datetime) -> Select:
    if filters.statuses:
        stmt = stmt.where(Task.status.in_(tuple(filters.statuses)))
    if filters.category:
        stmt = stmt.where(Task.category == filters.category)
    if filters.severity:
        stmt = stmt.where(Task.severity == filters.severity)
    if filters.source_type:
        stmt = stmt.where(Task.source_type == filters.source_type)
    if filters.patient_id:
        stmt = stmt.where(Task.patient_id == filters.patient_id)
    if filters.assignee == "unassigned":
        stmt = stmt.where(Task.assigned_to_user_id.is_(None))
    elif filters.assignee == "me":
        stmt = stmt.where(Task.assigned_to_user_id == filters.actor_user_id)
    elif filters.assignee:
        stmt = stmt.where(Task.assigned_to_user_id == filters.assignee)
    if filters.overdue:
        stmt = stmt.where(Task.due_at.is_not(None), Task.due_at < now, Task.status.in_(OPEN_STATUSES))
    if filters.due_before:
        stmt = stmt.where(Task.due_at.is_not(None), Task.due_at < filters.due_before)
    if filters.query:
        like = f"%{filters.query.strip()}%"
        stmt = stmt.where(or_(Task.title.ilike(like), Task.dedupe_key.ilike(like)))
    return stmt


async def list_tasks(
    session: AsyncSession, filters: TaskFilters, *, now: Optional[datetime] = None
) -> TaskPage:
    """One page of the inbox, plus the unpaginated total.

    Offset paging rather than a keyset cursor: the default order is
    (severity, due date), which is not monotonic, so a cursor would be fragile
    for no gain at the depth an inbox is actually read to.
    """
    moment = now or _now()
    limit = max(1, min(filters.limit, 200))
    offset = max(0, filters.offset)

    base = _apply_filters(select(Task), filters, moment)
    total = await session.scalar(_apply_filters(select(func.count()).select_from(Task), filters, moment))

    if filters.sort == "due":
        order = (Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.desc())
    elif filters.sort == "created":
        order = (Task.created_at.desc(),)
    else:
        order = (_severity_order().asc(), Task.due_at.is_(None), Task.due_at.asc())

    rows = (await session.scalars(base.order_by(*order).limit(limit).offset(offset))).all()
    return TaskPage(items=list(rows), total_count=int(total or 0), limit=limit, offset=offset)


async def task_events(session: AsyncSession, task_id: str) -> List[TaskEvent]:
    rows = await session.scalars(
        select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at.asc())
    )
    return list(rows.all())


async def open_task_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(Task).where(Task.status.in_(OPEN_STATUSES)))
        or 0
    )


__all__ = [
    "OPEN_STATUSES",
    "TERMINAL_STATUSES",
    "TRANSITIONS",
    "SYSTEM_ONLY_ACTIONS",
    "EVENT_FOR_ACTION",
    "EVENT_FOR_STATUS",
    "MAX_SNOOZE",
    "REOPEN_WINDOW",
    "MAX_ESCALATION_LEVEL",
    "SEVERITY_RANK",
    "TaskTransitionError",
    "TaskFilters",
    "TaskPage",
    "create_task",
    "transition",
    "comment",
    "close_tasks_for_source",
    "reopen_due_snoozed",
    "list_tasks",
    "task_events",
    "open_task_count",
]
