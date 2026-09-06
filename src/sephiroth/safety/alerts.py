"""Turns the read-time risk flags from `sephiroth.safety.risk` into
persisted `Alert` rows.

`assess_patient_risk` is deliberately never persisted (decision #10 in
CLAUDE.md — computed fresh from current labs/medications on every read).
`Alert` exists for a different reason: a clinician-facing workflow with
its own lifecycle (`active` -> `reviewed`/`resolved`, `reviewed_by`,
timestamps) that has to survive across requests. This module is the one
place that turns a transient flag into that persisted, actionable record
— idempotent, so it can run on every backend boot without ever
duplicating an alert a clinician hasn't resolved yet.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Alert, Patient
from sephiroth.safety.risk import assess_patient_risk
from sephiroth.workflows.events import CLINICAL_ALERT, emit

logger = logging.getLogger(__name__)

# risk.py flags use "lab"/"drug" as a free-form source; Alert.category is
# constrained (medication/lab/imaging/ai/clinical) — map the two flag
# sources actually produced today onto it.
_CATEGORY_BY_FLAG_SOURCE = {"lab": "lab", "drug": "medication"}

#: How long a resolved alert keeps its rule quiet.
#:
#: SPEC-021 said a resolved alert whose condition still holds may be raised
#: again, on the reasoning that a recurrence is new information. That is true
#: of a condition that goes away and comes back. It is false of a chronic one:
#: potassium that stays at 6.2, a standing drug pair the clinician has decided
#: to keep. For those, "resolved" means *I have dealt with this*, and the sweep
#: re-filing the same rule on its next pass is the inbox flooding this phase
#: set out to stop -- SPEC-020 made `alert_refresh` periodic, so it would land
#: every six hours rather than once per deploy.
#:
#: A window is the honest middle: the recurrence is still surfaced, but on a
#: clinical cadence rather than a sweep cadence. Seven days is chosen to be
#: longer than any sweep interval and shorter than a typical follow-up.
RESOLVED_SUPPRESSION = timedelta(days=7)


async def generate_alerts_for_patient(
    session: AsyncSession, patient: Patient, now: datetime | None = None
) -> List[Alert]:
    """Creates any `Alert` rows this patient's current risk flags call for
    and don't already have an open one. Returns the newly created rows
    (empty if nothing new)."""
    flags = assess_patient_risk(patient.lab_results, patient.medications, patient.allergies)
    if not flags:
        return []

    moment = now or datetime.now(timezone.utc).replace(tzinfo=None)

    # Everything not yet resolved, not just `active` (SPEC-021).
    #
    # This was the duplication defect: an alert a clinician had marked
    # `reviewed` but not resolved was absent from the set, so the next sweep
    # filed it again. It used to surface once per deploy, because
    # `generate_alerts_for_all_patients` only ran at boot. Since SPEC-020 made
    # `alert_refresh` genuinely periodic it would recur every six hours, which
    # is how a real inbox fills with copies of work somebody is already doing.
    existing = (await session.scalars(select(Alert).where(Alert.patient_id == patient.id))).all()
    existing_open = [a for a in existing if a.status != "resolved"]
    # Recently resolved rows suppress their rule too (see RESOLVED_SUPPRESSION).
    # `resolved_at` can be null on a row resolved before it was stamped, so
    # `created_at` stands in: an unknown resolution time is treated as recent
    # rather than as ancient, because the failure mode of the first is one
    # delayed alert and of the second is a flooded inbox.
    cutoff = moment - RESOLVED_SUPPRESSION

    def _recently_resolved(alert: Alert) -> bool:
        when = alert.resolved_at or alert.created_at
        return when is None or when > cutoff

    suppressed = [a for a in existing if a.status == "resolved" and _recently_resolved(a)]
    # Keyed on the rule, not the title. A title is display copy: rewording
    # "Hypokalemia" to "Low potassium" would otherwise duplicate every open
    # alert in the system at once. Pre-SPEC-021 rows have no `rule_key`, so
    # they fall back to the old key rather than being treated as absent.
    blocking = existing_open + suppressed
    already_open = {a.rule_key for a in blocking if a.rule_key}
    legacy_open = {(a.category, a.title) for a in blocking if not a.rule_key}

    created: List[Alert] = []
    for flag in flags:
        category = _CATEGORY_BY_FLAG_SOURCE.get(flag["source"], "clinical")
        title = flag["label"]
        rule_key = flag.get("rule_key") or f"legacy:{category}:{title}"
        if rule_key in already_open or (category, title) in legacy_open:
            continue
        alert = Alert(
            id=str(uuid.uuid4()),
            patient_id=patient.id,
            category=category,
            severity=flag["severity"],
            title=title,
            detail=flag["detail"],
            # The rule that fired, not just the engine that owns it -- a
            # warning a clinician cannot trace back to its threshold is one
            # they have to take on faith.
            source=flag.get("rule_source") or "risk_engine",
            rule_key=rule_key,
            kind=flag.get("kind", "clinical"),
        )
        session.add(alert)
        # SPEC-010: recorded in the same transaction as the Alert itself,
        # so an event can never exist for an alert that didn't actually
        # get created (or vice versa). No subscriber wired yet (Phase 9's
        # alert_escalation workflow is the first) -- the tick still
        # records it as `no_subscriber` rather than dropping it.
        emit(session, CLINICAL_ALERT, "alert", alert.id, patient_id=patient.id)
        created.append(alert)
        already_open.add(rule_key)  # guards duplicate flags within this same call

    return created


async def generate_alerts_for_all_patients(session: AsyncSession) -> int:
    """Runs `generate_alerts_for_patient` for every patient in the DB,
    commits, and returns the total number of new alerts created. Safe to
    call on every backend boot."""
    patients = (await session.scalars(select(Patient))).all()
    moment = datetime.now(timezone.utc).replace(tzinfo=None)
    total = 0
    for patient in patients:
        created = await generate_alerts_for_patient(session, patient, now=moment)
        total += len(created)
    if total:
        await session.commit()
        logger.info("Generated %d new alert(s) from current risk flags", total)
    return total


__all__ = [
    "generate_alerts_for_patient",
    "generate_alerts_for_all_patients",
    "RESOLVED_SUPPRESSION",
]
