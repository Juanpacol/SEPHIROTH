"""Whether now is a bad time to message a patient.

`quiet_hours` has been a validated, stored, documented setting that read as a
promise and did nothing (`memory.py`'s own docstring says so). What was missing
was not the lookup — it is three lines — but the engine's ability to say "not
now, ask me later", which is why this lands with the `deferred` outcome and not
before it.

**Scope: patient-facing steps only.** An alert escalation at 03:00 is precisely
the case escalation exists for, and `clinical_notify` tells a clinician about a
critical finding. Quiet hours are a patient-comfort setting, not a clinical
safety control, and applying them to either would mean the setting can silence
an emergency. `alert_escalation` and `clinical_notify` deliberately never call
this module.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from sephiroth.workflows.policy import quiet_window_end

from .memory import get_memory

#: `clinic` has no backing table (single-tenant, CLAUDE.md #7), so any id is
#: accepted; `/preferences` writes under this one.
CLINIC_SCOPE_ID = "default"


def clinic_timezone() -> tzinfo:
    """Quiet hours are wall-clock, so they need a wall.

    Falls back to UTC rather than raising: a typo in the setting should make
    the window wrong, not take the tick down.
    """
    try:
        return ZoneInfo(settings.clinic_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        from datetime import timezone

        return timezone.utc


def clinic_today() -> date:
    """The clinic's calendar day, not the server's.

    Every timestamp in this schema is naive UTC, so `date.today()` -- which
    reads the *host's* local zone -- gives a third answer that matches neither
    the data nor the clinic. On a UTC host in a UTC-5 clinic it rolls the day
    over at 7pm local; on a developer's laptop it rolls at a different hour
    again, so "once per day" means something different in each deployment.
    """
    return datetime.now(clinic_timezone()).date()


async def defer_for_quiet_hours(
    session: AsyncSession,
    now: datetime,
    *,
    patient_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[datetime]:
    """When to try again, or `None` if now is fine.

    Precedence is most-specific-first: this patient's own window, then the
    recipient's, then the clinic default. A patient who asked not to be
    messaged at night has said something more specific than the clinic's
    setting, and the more specific answer wins.
    """
    for scope, scope_id in (
        ("patient", patient_id),
        ("user", user_id),
        ("clinic", CLINIC_SCOPE_ID),
    ):
        if not scope_id:
            continue
        window = await get_memory(session, scope, scope_id, "quiet_hours")
        if not isinstance(window, dict):
            continue
        closes = quiet_window_end(now, window.get("start", ""), window.get("end", ""), clinic_timezone())
        # A window that exists and does not cover `now` is still an answer:
        # stop here rather than falling through to a broader scope that might
        # say otherwise.
        return closes

    return None


__all__ = ["defer_for_quiet_hours", "clinic_timezone", "clinic_today", "CLINIC_SCOPE_ID"]
