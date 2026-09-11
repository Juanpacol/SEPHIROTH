"""Daily synthetic-data pipeline, scheduling half — keeps the Agenda/
Schedule week view showing real day-over-day movement: new appointments
appearing, some getting marked completed or no-show, so the calendar isn't
permanently empty for a fresh clinician account.

Every patient in this database is confirmed synthetic (portfolio MVP) --
appointments booked here are between a real clinician account and a
synthetic patient. Inserted directly (bypassing `POST /api/scheduling/
appointments`), same posture as `synthetic_daily`'s direct `LabResult`
inserts -- this deliberately does NOT emit `NEW_APPOINTMENT` (no reminder
workflow / no unconfirmed-at-T-2h alert for a backdated synthetic booking),
since that workflow exists to nudge a *real* patient, not to generate
demo noise.

Reuses `platform.api.scheduling.expand_slots` (the same pure slot-expansion
function the real booking endpoint uses) so a synthetic appointment can
never land outside a clinician's actual working hours or overlap an
existing booking -- no separate scheduling logic to keep in sync.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import date, datetime, time, timedelta
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Appointment, AvailabilityException, AvailabilityRule, Patient, User

logger = logging.getLogger(__name__)

# Mon-Fri, 9:00-17:00, 30-minute slots -- a plain default work week. Only
# ever inserted for a clinician with zero existing rules (see
# ensure_default_availability), so it never overrides hours a clinician set
# themselves through the UI.
_DEFAULT_WEEKDAYS = (0, 1, 2, 3, 4)
_DEFAULT_START = time(9, 0)
_DEFAULT_END = time(17, 0)
_DEFAULT_SLOT_MINUTES = 30

_REASONS = (
    "Follow-up visit",
    "Annual checkup",
    "Medication review",
    "Lab results review",
    "New patient consultation",
    "Chronic condition management",
)

_LOOKAHEAD_DAYS = 10
_MAX_NEW_PER_CLINICIAN_PER_DAY = 3
_MAX_UPCOMING_PER_CLINICIAN = 20
_NO_SHOW_PROBABILITY = 0.1


async def ensure_default_availability(session: AsyncSession, clinicians: List[User]) -> int:
    """Seeds the Mon-Fri 9-17 default for any active clinician with zero
    `AvailabilityRule` rows -- a synthetic booking (and the real booking
    endpoint) both need at least one rule to compute slots from. Never
    touches a clinician who already has rules, however sparse."""
    seeded = 0
    for clinician in clinicians:
        existing = await session.scalar(
            select(AvailabilityRule.id).where(AvailabilityRule.clinician_id == clinician.id).limit(1)
        )
        if existing is not None:
            continue
        for weekday in _DEFAULT_WEEKDAYS:
            session.add(
                AvailabilityRule(
                    id=str(uuid.uuid4()),
                    clinician_id=clinician.id,
                    weekday=weekday,
                    start_time=_DEFAULT_START,
                    end_time=_DEFAULT_END,
                    timezone="UTC",
                    slot_minutes=_DEFAULT_SLOT_MINUTES,
                )
            )
        seeded += 1
    return seeded


async def transition_past_appointments(session: AsyncSession, clinicians: List[User], now: datetime) -> Tuple[int, int]:
    """Any `booked` appointment whose end has already passed becomes
    `completed` (the common case) or occasionally `no_show` -- a clinic's
    booked-forever calendar is not realistic, and the Schedule week view
    only distinguishes completed (green) from everything else (blue), so
    this is what actually produces visible movement on past days."""
    clinician_ids = [c.id for c in clinicians]
    if not clinician_ids:
        return 0, 0

    past_due = (
        await session.scalars(
            select(Appointment).where(
                Appointment.clinician_id.in_(clinician_ids),
                Appointment.status == "booked",
                Appointment.end_at < now,
            )
        )
    ).all()

    completed = no_show = 0
    for appt in past_due:
        if random.random() < _NO_SHOW_PROBABILITY:
            appt.status = "no_show"
            no_show += 1
        else:
            appt.status = "completed"
            completed += 1
    return completed, no_show


async def _load_clinician_schedule(
    session: AsyncSession, clinician_id: str, start: date, end: date
) -> Tuple[List[AvailabilityRule], List[AvailabilityException], List[Appointment]]:
    rules = (
        await session.scalars(select(AvailabilityRule).where(AvailabilityRule.clinician_id == clinician_id))
    ).all()
    range_start = datetime.combine(start, time.min)
    range_end = datetime.combine(end, time.min)
    exceptions = (
        await session.scalars(
            select(AvailabilityException).where(
                AvailabilityException.clinician_id == clinician_id,
                AvailabilityException.start_at < range_end,
                AvailabilityException.end_at > range_start,
            )
        )
    ).all()
    appointments = (
        await session.scalars(
            select(Appointment).where(
                Appointment.clinician_id == clinician_id,
                Appointment.status == "booked",
                Appointment.start_at < range_end,
                Appointment.end_at > range_start,
            )
        )
    ).all()
    return list(rules), list(exceptions), list(appointments)


async def book_new_appointments(
    session: AsyncSession, clinician: User, patients: List[Patient], today: date
) -> int:
    """Books up to `_MAX_NEW_PER_CLINICIAN_PER_DAY` new synthetic
    appointments for this clinician into their own real working hours,
    over the next `_LOOKAHEAD_DAYS` days -- capped so the calendar fills up
    gradually instead of all at once, and stops growing once
    `_MAX_UPCOMING_PER_CLINICIAN` future bookings already exist."""
    if not patients:
        return 0

    horizon_end = today + timedelta(days=_LOOKAHEAD_DAYS)
    rules, exceptions, appointments = await _load_clinician_schedule(session, clinician.id, today, horizon_end)
    if not rules:
        return 0

    upcoming_count = len(appointments)
    if upcoming_count >= _MAX_UPCOMING_PER_CLINICIAN:
        return 0

    from api.scheduling import expand_slots  # local import: platform/ isn't a package, see CLAUDE.md

    open_slots = expand_slots(rules, exceptions, appointments, today, horizon_end)
    if not open_slots:
        return 0

    to_book = min(
        _MAX_NEW_PER_CLINICIAN_PER_DAY,
        _MAX_UPCOMING_PER_CLINICIAN - upcoming_count,
        len(open_slots),
    )
    chosen_slots = random.sample(open_slots, to_book)

    booked = 0
    for slot in chosen_slots:
        patient = random.choice(patients)
        appt = Appointment(
            id=str(uuid.uuid4()),
            clinician_id=clinician.id,
            patient_id=patient.id,
            start_at=slot.start_at,
            end_at=slot.end_at,
            status="booked",
            reason=random.choice(_REASONS),
            created_by_user_id=clinician.id,
        )
        session.add(appt)
        try:
            # Flushed one at a time so a same-day overlap this loop itself
            # created (two random slots colliding is impossible here since
            # expand_slots already de-dupes candidates, but a concurrent
            # tick invocation is not) raises here, not at the final commit,
            # so the rest of this clinician's batch can still succeed.
            await session.flush()
        except IntegrityError:
            await session.rollback()
            continue
        booked += 1
    return booked


async def run_daily_schedule_simulation(session: AsyncSession, *, today: date) -> dict:
    """One pass: seed default hours for any bare clinician, retire past
    bookings into completed/no_show, then book a few new ones per
    clinician. Called from `synthetic_daily.run_daily_simulation` --
    kept as a separate module since scheduling and labs are independent
    concerns, but folded into the same daily run and summary."""
    clinicians = (
        await session.scalars(select(User).where(User.role == "clinician", User.is_active.is_(True)))
    ).all()
    clinicians = list(clinicians)

    availability_rules_seeded = await ensure_default_availability(session, clinicians)
    completed, no_show = await transition_past_appointments(
        session, clinicians, datetime.combine(today, time.min)
    )

    patients = list((await session.scalars(select(Patient))).all())
    booked = 0
    for clinician in clinicians:
        booked += await book_new_appointments(session, clinician, patients, today)

    return {
        "clinicians_touched": len(clinicians),
        "availability_rules_seeded": availability_rules_seeded,
        "appointments_booked": booked,
        "appointments_completed": completed,
        "appointments_no_show": no_show,
    }


__all__ = [
    "run_daily_schedule_simulation",
    "ensure_default_availability",
    "transition_past_appointments",
    "book_new_appointments",
]
