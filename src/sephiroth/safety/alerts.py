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
from datetime import datetime, timezone
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


async def generate_alerts_for_patient(session: AsyncSession, patient: Patient) -> List[Alert]:
    """Creates any `Alert` rows this patient's current risk flags call for
    and don't already have an open one. Returns the newly created rows
    (empty if nothing new)."""
    flags = assess_patient_risk(patient.lab_results, patient.medications)
    if not flags:
        return []

    existing_active = (
        await session.scalars(select(Alert).where(Alert.patient_id == patient.id, Alert.status == "active"))
    ).all()
    already_open = {(a.category, a.title) for a in existing_active}

    created: List[Alert] = []
    for flag in flags:
        category = _CATEGORY_BY_FLAG_SOURCE.get(flag["source"], "clinical")
        title = flag["label"]
        if (category, title) in already_open:
            continue
        alert = Alert(
            id=str(uuid.uuid4()),
            patient_id=patient.id,
            category=category,
            severity=flag["severity"],
            title=title,
            detail=flag["detail"],
            source="risk_engine",
        )
        session.add(alert)
        # SPEC-010: recorded in the same transaction as the Alert itself,
        # so an event can never exist for an alert that didn't actually
        # get created (or vice versa). No subscriber wired yet (Phase 9's
        # alert_escalation workflow is the first) -- the tick still
        # records it as `no_subscriber` rather than dropping it.
        emit(session, CLINICAL_ALERT, "alert", alert.id, patient_id=patient.id)
        created.append(alert)
        already_open.add((category, title))  # guards duplicate flags within this same call

    return created


async def generate_alerts_for_all_patients(session: AsyncSession) -> int:
    """Runs `generate_alerts_for_patient` for every patient in the DB,
    commits, and returns the total number of new alerts created. Safe to
    call on every backend boot."""
    patients = (await session.scalars(select(Patient))).all()
    total = 0
    for patient in patients:
        created = await generate_alerts_for_patient(session, patient)
        total += len(created)
    if total:
        await session.commit()
        logger.info("Generated %d new alert(s) from current risk flags", total)
    return total


async def resolve_recovered_alerts_for_patient(session: AsyncSession, patient: Patient) -> int:
    """Auto-resolves this patient's active, risk-engine-generated alerts
    whose flag no longer applies under the patient's *current*
    labs/medications -- the inverse of `generate_alerts_for_patient`.

    Deliberately NOT wired into the boot-time `generate_alerts_for_all_patients`
    path: auto-clearing an alert just because a value is transiently back in
    range is a real clinical-safety call a clinician should make, not
    something this app should do silently for real patients. Only called
    from `sephiroth.safety.synthetic_daily` (every patient here is confirmed
    synthetic) so day-over-day "recovery" in the synthetic-data pipeline is
    reflected in the alert list too, not just in the underlying labs.

    Only ever touches `source == "risk_engine"` rows -- an alert a clinician
    or another engine raised is never auto-resolved here."""
    still_open = {
        (_CATEGORY_BY_FLAG_SOURCE.get(flag["source"], "clinical"), flag["label"])
        for flag in assess_patient_risk(patient.lab_results, patient.medications)
    }
    existing_active = (
        await session.scalars(
            select(Alert).where(
                Alert.patient_id == patient.id,
                Alert.status == "active",
                Alert.source == "risk_engine",
            )
        )
    ).all()

    resolved = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for alert in existing_active:
        if (alert.category, alert.title) in still_open:
            continue
        alert.status = "resolved"
        alert.resolved_at = now
        resolved += 1
    return resolved


async def resolve_recovered_alerts_for_all_patients(session: AsyncSession) -> int:
    """`resolve_recovered_alerts_for_patient` for every patient, commits,
    returns the total resolved. See that function's docstring for why this
    is not part of the boot-time alert path."""
    patients = (await session.scalars(select(Patient))).all()
    total = 0
    for patient in patients:
        total += await resolve_recovered_alerts_for_patient(session, patient)
    if total:
        await session.commit()
        logger.info("Auto-resolved %d recovered alert(s)", total)
    return total


__all__ = [
    "generate_alerts_for_patient",
    "generate_alerts_for_all_patients",
    "resolve_recovered_alerts_for_patient",
    "resolve_recovered_alerts_for_all_patients",
]
