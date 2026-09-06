"""The task state machine (SPEC-018 §6.3).

Every cell of the transition table, and — more importantly — the cells that
are *not* in it. A permissive state machine is worse than none: it lets a
clinician close work from a state where closing means something different, and
nothing downstream can tell the difference afterwards.

Verifies AC-018-03, AC-018-04, AC-018-05, AC-018-06
(docs/specs/SPEC-018-unified-tasks.md).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from api.services import task_service as svc
from api.services.task_service import TaskTransitionError
from data.schemas import Patient, Task, TaskEvent, User

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 12, 0, 0)


async def _patient(session, pid="PT1"):
    p = Patient(id=pid, name="Ana Ruiz", age=54, sex="F", medical_record_number=f"MRN-{pid}")
    session.add(p)
    await session.flush()
    return p


async def _user(session, name="Dra. Ruiz", active=True):
    u = User(
        id=str(uuid4()),
        email=f"{uuid4().hex[:8]}@example.test",
        name=name,
        hashed_password="x",
        role="clinician",
        is_active=active,
    )
    session.add(u)
    await session.flush()
    return u


async def _task(session, *, severity="high", status="open", closed_by=None, **kwargs):
    patient = await _patient(session, kwargs.pop("pid", f"PT{uuid4().hex[:6]}"))
    # Created up front, not lazily below: `_user` flushes, and a flush issued
    # while the task is already dirty with status='done' and closed_by=NULL
    # trips `ck_task_closed_requires_actor` before the actor is ever assigned.
    actor_id = closed_by
    if status in ("done", "dismissed") and actor_id is None:
        actor_id = (await _user(session, "Dr. Fixture")).id
    task, _ = await svc.create_task(
        session,
        source_type="alert",
        source_id=str(uuid4()),
        category="alert",
        severity=severity,
        title="Critical potassium",
        dedupe_key=f"alert:{uuid4()}",
        patient_id=patient.id,
        now=NOW,
        **kwargs,
    )
    if status != "open":
        task.status = status
        if status in ("done", "dismissed"):
            # `ck_task_closed_requires_actor` refuses a closed task with nobody
            # against it, so a fixture that forces one has to supply the actor
            # the real transition would have recorded.
            task.closed_at = NOW
            task.closed_by = actor_id
        elif status == "superseded":
            task.closed_at = NOW
    await session.flush()
    return task


class TestAllowedTransitions:
    async def test_claim_takes_an_unassigned_task(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)

        await svc.transition(db_session, task, "claim", actor=actor, now=NOW)

        assert task.status == "in_progress"
        assert task.assigned_to_user_id == actor.id

    async def test_complete_records_who_closed_it(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)

        await svc.transition(db_session, task, "complete", actor=actor, now=NOW)

        assert task.status == "done"
        assert task.closed_by == actor.id
        assert task.closed_at == NOW

    async def test_snooze_sets_a_wake_time_and_resume_clears_it(self, db_session):
        task = await _task(db_session, severity="medium")
        actor = await _user(db_session)
        wake = NOW + timedelta(hours=6)

        await svc.transition(db_session, task, "snooze", actor=actor, snooze_until=wake, now=NOW)
        assert (task.status, task.snoozed_until) == ("snoozed", wake)

        await svc.transition(db_session, task, "resume", actor=actor, now=NOW)
        assert (task.status, task.snoozed_until) == ("in_progress", None)

    async def test_escalate_raises_the_level_without_changing_status(self, db_session):
        task = await _task(db_session)

        await svc.transition(db_session, task, "escalate", actor=None, now=NOW)

        # An escalated task is still open work — the same reasoning that keeps
        # Appointment.confirmed_at out of Appointment.status.
        assert task.status == "open"
        assert (task.escalation_level, task.escalated_at) == (1, NOW)

    async def test_reopen_clears_the_closure(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)
        await svc.transition(db_session, task, "dismiss", actor=actor, reason="duplicate", now=NOW)

        await svc.transition(db_session, task, "reopen", actor=actor, now=NOW + timedelta(days=1))

        assert task.status == "open"
        assert task.closed_at is None
        assert task.closed_by is None
        assert task.dismiss_reason == ""


class TestRejectedTransitions:
    async def test_every_pair_absent_from_the_table_is_refused(self, db_session):
        """The table is the contract; anything outside it must raise rather
        than fall through to a default."""
        actor = await _user(db_session)
        statuses = ("open", "in_progress", "snoozed", "done", "dismissed", "superseded")
        actions = tuple({a for _, a in svc.TRANSITIONS})

        for status in statuses:
            for action in actions:
                if (status, action) in svc.TRANSITIONS:
                    continue
                task = await _task(db_session, status=status)
                with pytest.raises(TaskTransitionError):
                    await svc.transition(
                        db_session,
                        task,
                        action,
                        actor=actor,
                        now=NOW,
                        snooze_until=NOW + timedelta(hours=1),
                        reason="because",
                        assignee_id=actor.id,
                    )

    async def test_superseded_is_terminal_even_for_reopen(self, db_session):
        task = await _task(db_session, status="superseded")
        actor = await _user(db_session)

        with pytest.raises(TaskTransitionError):
            await svc.transition(db_session, task, "reopen", actor=actor, now=NOW)

    async def test_claim_refuses_a_task_someone_else_holds(self, db_session):
        task = await _task(db_session)
        holder = await _user(db_session, "Dr. Otro")
        newcomer = await _user(db_session, "Dra. Nueva")
        await svc.transition(db_session, task, "claim", actor=holder, now=NOW)
        task.status = "open"  # back to the pool without releasing the assignee

        with pytest.raises(TaskTransitionError, match="already claimed"):
            await svc.transition(db_session, task, "claim", actor=newcomer, now=NOW)

    async def test_a_critical_task_cannot_be_snoozed(self, db_session):
        task = await _task(db_session, severity="critical")
        actor = await _user(db_session)

        with pytest.raises(TaskTransitionError, match="critical"):
            await svc.transition(
                db_session, task, "snooze", actor=actor, snooze_until=NOW + timedelta(hours=2), now=NOW
            )

    async def test_snooze_is_capped_and_must_be_in_the_future(self, db_session):
        actor = await _user(db_session)

        past = await _task(db_session, severity="low")
        with pytest.raises(TaskTransitionError, match="future"):
            await svc.transition(
                db_session, past, "snooze", actor=actor, snooze_until=NOW - timedelta(hours=1), now=NOW
            )

        far = await _task(db_session, severity="low")
        with pytest.raises(TaskTransitionError, match="7 days"):
            await svc.transition(
                db_session, far, "snooze", actor=actor, snooze_until=NOW + timedelta(days=8), now=NOW
            )

    async def test_dismiss_requires_a_reason(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)

        with pytest.raises(TaskTransitionError, match="reason"):
            await svc.transition(db_session, task, "dismiss", actor=actor, reason="   ", now=NOW)

    async def test_assign_refuses_an_inactive_user(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)
        retired = await _user(db_session, "Dr. Retirado", active=False)

        with pytest.raises(TaskTransitionError, match="active"):
            await svc.transition(db_session, task, "assign", actor=actor, assignee_id=retired.id, now=NOW)

    async def test_supersede_is_system_only(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)

        with pytest.raises(TaskTransitionError, match="system action"):
            await svc.transition(db_session, task, "supersede", actor=actor, now=NOW)

        # ...and works with no actor.
        await svc.transition(db_session, task, "supersede", actor=None, now=NOW)
        assert task.status == "superseded"

    async def test_closing_requires_a_clinician(self, db_session):
        """`ck_task_closed_requires_actor` would refuse the write anyway; the
        service fails first so the error says why."""
        task = await _task(db_session)

        with pytest.raises(TaskTransitionError, match="requires a clinician"):
            await svc.transition(db_session, task, "complete", actor=None, now=NOW)

    async def test_reopen_window_expires(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)
        await svc.transition(db_session, task, "complete", actor=actor, now=NOW)

        with pytest.raises(TaskTransitionError, match="reopen window"):
            await svc.transition(db_session, task, "reopen", actor=actor, now=NOW + timedelta(days=31))

    async def test_escalation_stops_at_the_top_level(self, db_session):
        task = await _task(db_session)
        for _ in range(svc.MAX_ESCALATION_LEVEL):
            await svc.transition(db_session, task, "escalate", actor=None, now=NOW)

        with pytest.raises(TaskTransitionError, match="highest escalation"):
            await svc.transition(db_session, task, "escalate", actor=None, now=NOW)


class TestHistory:
    async def test_every_transition_records_who_did_what(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)

        await svc.transition(db_session, task, "claim", actor=actor, now=NOW)
        await svc.transition(db_session, task, "complete", actor=actor, now=NOW)
        await db_session.flush()

        events = await svc.task_events(db_session, task.id)
        assert [e.event_type for e in events] == ["created", "claimed", "completed"]
        # Creation is the system's doing; the rest is a person's.
        assert events[0].actor_user_id is None
        assert {e.actor_user_id for e in events[1:]} == {actor.id}
        assert (events[-1].from_status, events[-1].to_status) == ("in_progress", "done")

    async def test_event_types_stay_inside_the_database_constraint(self, db_session):
        """Every action's recorded event_type must be one the CHECK allows —
        derived names like "dismissd" would only fail at write time."""
        allowed = {
            "created",
            "claimed",
            "assigned",
            "snoozed",
            "resumed",
            "escalated",
            "completed",
            "dismissed",
            "superseded",
            "reopened",
            "commented",
        }
        assert set(svc.EVENT_FOR_ACTION.values()) <= allowed
        assert set(svc.EVENT_FOR_STATUS.values()) <= allowed
        assert set(svc.EVENT_FOR_ACTION) == {a for _, a in svc.TRANSITIONS}

    async def test_a_comment_is_recorded_without_moving_the_task(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)

        await svc.comment(db_session, task, actor=actor, body="  called the lab  ")
        await db_session.flush()

        events = await svc.task_events(db_session, task.id)
        assert events[-1].event_type == "commented"
        assert events[-1].note == "called the lab"
        assert task.status == "open"

    async def test_an_empty_comment_is_refused(self, db_session):
        task = await _task(db_session)
        actor = await _user(db_session)

        with pytest.raises(TaskTransitionError):
            await svc.comment(db_session, task, actor=actor, body="   ")


class TestSnoozeExpiry:
    async def test_the_tick_reopens_tasks_whose_snooze_ran_out(self, db_session):
        actor = await _user(db_session)
        due = await _task(db_session, severity="low")
        await svc.transition(
            db_session, due, "snooze", actor=actor, snooze_until=NOW + timedelta(hours=1), now=NOW
        )
        still_asleep = await _task(db_session, severity="low")
        await svc.transition(
            db_session, still_asleep, "snooze", actor=actor, snooze_until=NOW + timedelta(days=3), now=NOW
        )
        await db_session.flush()

        reopened = await svc.reopen_due_snoozed(db_session, now=NOW + timedelta(hours=2))

        assert reopened == 1
        await db_session.refresh(due)
        await db_session.refresh(still_asleep)
        assert (due.status, due.snoozed_until) == ("open", None)
        assert still_asleep.status == "snoozed"

    async def test_expiry_records_no_event_because_nobody_did_it(self, db_session):
        actor = await _user(db_session)
        task = await _task(db_session, severity="low")
        await svc.transition(
            db_session, task, "snooze", actor=actor, snooze_until=NOW + timedelta(hours=1), now=NOW
        )
        await db_session.flush()
        before = len(await svc.task_events(db_session, task.id))

        await svc.reopen_due_snoozed(db_session, now=NOW + timedelta(hours=2))
        await db_session.flush()

        assert len(await svc.task_events(db_session, task.id)) == before


class TestDatabaseConstraints:
    async def test_a_closed_task_cannot_lack_an_actor(self, db_session):
        """The service guards this, but the constraint is what makes the audit
        query "closed with nobody against it" reliably return nothing."""
        from sqlalchemy.exc import IntegrityError

        patient = await _patient(db_session, "PTX")
        db_session.add(
            Task(
                id=str(uuid4()),
                dedupe_key="manual:1",
                source_type="alert",
                category="alert",
                patient_id=patient.id,
                title="hand-written",
                severity="high",
                status="done",
                closed_by=None,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_two_tasks_cannot_share_a_dedupe_key(self, db_session):
        from sqlalchemy.exc import IntegrityError

        patient = await _patient(db_session, "PTY")
        for _ in range(2):
            db_session.add(
                Task(
                    id=str(uuid4()),
                    dedupe_key="alert:same",
                    source_type="alert",
                    category="alert",
                    patient_id=patient.id,
                    title="dup",
                    severity="high",
                )
            )
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_clinical_detail_round_trips_through_the_encrypted_column(self, db_session):
        task = await _task(db_session, detail="K+ 6.8 mmol/L, repeat drawn")
        await db_session.flush()

        stored = await db_session.get(Task, task.id)
        assert stored is not None and stored.detail == "K+ 6.8 mmol/L, repeat drawn"
        assert isinstance(stored.context, dict)
        assert isinstance(await svc.task_events(db_session, task.id), list)
        assert isinstance(stored.created_at, datetime)
        assert isinstance(await db_session.get(TaskEvent, 1), (TaskEvent, type(None)))
