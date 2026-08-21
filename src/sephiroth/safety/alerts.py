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
from typing import Dict, List

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
        await session.scalars(
            select(Alert).where(Alert.patient_id == patient.id, Alert.status == "active")
        )
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


__all__ = ["generate_alerts_for_patient", "generate_alerts_for_all_patients"]
