"""Appointments nobody came to, and reminders that survive a reschedule.

`Appointment.status` has had a `no_show` value since scheduling shipped and
nothing but a clinician remembering could set it, so the number measured how
diligently people annotate the calendar. `MISSED_APPOINTMENT` was a declared
event type with no producer at all.

The grace period is the design: a booking that ended twenty minutes ago is an
appointment whose notes are not written yet, not a no-show.

Verifies AC-020-07, AC-020-08 (docs/specs/SPEC-020-automation-correctness.md).
"""

from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.workflows.no_show import sweep_missed_appointments
from data.schemas import Appointment, Patient, User, Workflow, WorkflowEvent, WorkflowStep

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 12, 0, 0)


async def _clinician(session):
    u = User(
        id=str(uuid4()),
        email=f"{uuid4().hex[:8]}@example.test",
        name="Dra. NS",
        hashed_password="x",
        role="clinician",
    )
    session.add(u)
    await session.flush()
    return u


async def _appointment(session, *, ends_ago: timedelta, status="booked", pid=None):
    pid = pid or f"PNS{uuid4().hex[:5]}"
    patient = Patient(id=pid, name="NS", age=40, sex="F", medical_record_number=f"MRN-{pid}")
    session.add(patient)
    clinician = await _clinician(session)
    end_at = NOW - ends_ago
    appt = Appointment(
        id=str(uuid4()),
        patient_id=patient.id,
        clinician_id=clinician.id,
        start_at=end_at - timedelta(minutes=20),
        end_at=end_at,
        status=status,
        reason="control",
    )
    session.add(appt)
    await session.flush()
    return appt


class TestSweep:
    async def test_a_long_past_booking_becomes_a_no_show(self, db_session):
        appt = await _appointment(db_session, ends_ago=timedelta(hours=25))

        count = await sweep_missed_appointments(db_session, NOW)
        await db_session.flush()

        assert count == 1
        await db_session.refresh(appt)
        assert appt.status == "no_show"

    async def test_a_recently_ended_booking_is_left_alone(self, db_session):
        """It is an appointment whose notes are not written yet."""
        appt = await _appointment(db_session, ends_ago=timedelta(hours=1))

        assert await sweep_missed_appointments(db_session, NOW) == 0
        await db_session.refresh(appt)
        assert appt.status == "booked"

    async def test_a_clinician_who_already_annotated_it_wins(self, db_session):
        for status in ("completed", "cancelled", "no_show"):
            appt = await _appointment(db_session, ends_ago=timedelta(days=3), status=status)
            await sweep_missed_appointments(db_session, NOW)
            await db_session.refresh(appt)
            assert appt.status == status

    async def test_it_emits_the_event_that_had_no_producer(self, db_session):
        appt = await _appointment(db_session, ends_ago=timedelta(hours=30))

        await sweep_missed_appointments(db_session, NOW)
        await db_session.flush()

        events = (
            await db_session.scalars(
                select(WorkflowEvent).where(WorkflowEvent.event_type == "MISSED_APPOINTMENT")
            )
        ).all()
        assert len(events) == 1
        assert events[0].entity_id == appt.id
        assert events[0].patient_id == appt.patient_id

    async def test_running_it_twice_does_not_emit_twice(self, db_session):
        await _appointment(db_session, ends_ago=timedelta(hours=30))

        first = await sweep_missed_appointments(db_session, NOW)
        await db_session.flush()
        second = await sweep_missed_appointments(db_session, NOW)
        await db_session.flush()

        assert (first, second) == (1, 0)
        events = (
            await db_session.scalars(
                select(WorkflowEvent).where(WorkflowEvent.event_type == "MISSED_APPOINTMENT")
            )
        ).all()
        assert len(events) == 1

    async def test_it_cancels_work_that_was_about_that_appointment(self, db_session):
        """A reminder still pending for an appointment that has been and gone
        is about something that already happened."""
        appt = await _appointment(db_session, ends_ago=timedelta(hours=30))
        workflow = Workflow(
            id=str(uuid4()),
            definition_key="appointment_reminder",
            patient_id=appt.patient_id,
            appointment_id=appt.id,
            status="active",
            context={},
        )
        db_session.add(workflow)
        step = WorkflowStep(
            id=str(uuid4()),
            workflow_id=workflow.id,
            step_key="reminder_t24",
            step_type="appointment_reminder_t24",
            status="pending",
            due_at=NOW - timedelta(days=2),
            run_after=NOW - timedelta(days=2),
        )
        db_session.add(step)
        await db_session.flush()

        await sweep_missed_appointments(db_session, NOW)
        await db_session.flush()

        await db_session.refresh(workflow)
        await db_session.refresh(step)
        assert workflow.status == "cancelled"
        assert step.status == "cancelled"

    async def test_the_grace_period_is_configurable(self, db_session, monkeypatch):
        monkeypatch.setattr("core.config.settings.no_show_grace_hours", 2)
        appt = await _appointment(db_session, ends_ago=timedelta(hours=3))

        assert await sweep_missed_appointments(db_session, NOW) == 1
        await db_session.refresh(appt)
        assert appt.status == "no_show"


class TestRescheduleReenrols:
    async def test_rescheduling_re_emits_so_the_reminder_comes_back(self, db_session):
        """The defect this closes: `_load_live_appointment` correctly returned
        `superseded` after a reschedule, so nothing fired against stale data —
        but the workflow stayed active, `on_new_appointment`'s idempotency
        guard would then refuse a replacement, and no event was emitted anyway.
        The result was an appointment with no reminder and nothing to say so.
        """
        from httpx import ASGITransport, AsyncClient

        from api.main import app
        from core.db import get_session

        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        try:
            client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
            res = await client.post(
                "/api/auth/register",
                json={"email": f"{uuid4().hex[:8]}@ex.org", "name": "Dra. R", "password": "password123"},
            )
            headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
            me = (await client.get("/api/auth/me", headers=headers)).json()

            patient = Patient(id="PRS1", name="Resched", age=44, sex="F", medical_record_number="MRN-PRS1")
            db_session.add(patient)
            start = datetime.combine(date.today() + timedelta(days=10), time(14, 0))
            appt = Appointment(
                id="ARS1",
                patient_id="PRS1",
                clinician_id=me["id"],
                start_at=start,
                end_at=start + timedelta(minutes=20),
                status="booked",
            )
            db_session.add(appt)
            workflow = Workflow(
                id=str(uuid4()),
                definition_key="appointment_reminder",
                patient_id="PRS1",
                appointment_id="ARS1",
                status="active",
                context={"start_at": start.isoformat()},
            )
            db_session.add(workflow)
            await db_session.commit()

            new_start = (start + timedelta(days=3)).replace(tzinfo=timezone.utc)
            patch = await client.patch(
                "/api/scheduling/appointments/ARS1",
                json={"start_at": new_start.isoformat()},
                headers=headers,
            )
            assert patch.status_code == 200

            await db_session.refresh(workflow)
            assert workflow.status == "cancelled"

            events = (
                await db_session.scalars(
                    select(WorkflowEvent).where(
                        WorkflowEvent.event_type == "NEW_APPOINTMENT",
                        WorkflowEvent.entity_id == "ARS1",
                    )
                )
            ).all()
            assert len(events) == 1, "the reschedule must re-enrol, not silently drop the reminder"
        finally:
            app.dependency_overrides.clear()
