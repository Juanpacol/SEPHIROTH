"""Appointments nobody came to.

`Appointment.status` has had a `no_show` value since scheduling shipped, and
the only thing that could ever set it was a clinician remembering to. So the
number was a measure of how diligently people annotate the calendar, and
`MISSED_APPOINTMENT` — a declared event type since the event catalog — had no
producer at all.

The grace period is the whole design. A booking that ended twenty minutes ago
is not a no-show; it is an appointment whose notes are not written yet. A day
later, with nobody having touched it, it is. `no_show_grace_hours` is generous
on purpose: a clinician marking yesterday's list `completed` over morning
coffee should win the race against the sweep every time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from data.schemas import Appointment, Workflow
from sephiroth.workflows.events import MISSED_APPOINTMENT, emit

from .instantiate import cancel_workflow

logger = logging.getLogger(__name__)


async def sweep_missed_appointments(
    session: AsyncSession, now: Optional[datetime] = None, limit: int = 100
) -> int:
    """Mark long-past, still-booked appointments as no-shows. Returns the count.

    Does not commit — the tick owns the transaction.
    """
    moment = now or datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = moment - timedelta(hours=settings.no_show_grace_hours)

    stale = (
        await session.scalars(
            select(Appointment)
            .where(Appointment.status == "booked", Appointment.end_at < cutoff)
            .order_by(Appointment.end_at)
            .limit(limit)
        )
    ).all()

    for appt in stale:
        appt.status = "no_show"
        emit(
            session,
            MISSED_APPOINTMENT,
            "appointment",
            appt.id,
            patient_id=appt.patient_id,
            payload={"start_at": appt.start_at.isoformat(), "reason": appt.reason or ""},
        )
        # Any reminder or unconfirmed-check still pending for it is now about
        # an appointment that has already been and gone.
        for workflow in (
            await session.scalars(
                select(Workflow).where(Workflow.appointment_id == appt.id, Workflow.status == "active")
            )
        ).all():
            await cancel_workflow(session, workflow, moment)

    if stale:
        logger.info("marked %d appointment(s) as no_show", len(stale))
    return len(stale)


__all__ = ["sweep_missed_appointments"]
