"""What the clinician needs to know before the patient sits down.

Assembled on read from rows that already exist, and stored nowhere. A cached
brief is a brief that is wrong the moment a lab comes back, and the whole point
is that it is true at the moment it is opened.

No model runs here. Every line is a row somebody already wrote — the value is
that they are in one place, not that anything was inferred.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import (
    Alert,
    Appointment,
    Encounter,
    ImagingStudy,
    LabResult,
    Patient,
    Task,
)
from sephiroth.clinical.vitals import format_vitals
from sephiroth.safety.risk import assess_patient_risk

from . import task_service as svc

#: How much history is worth showing. Beyond this the brief stops being
#: something read in the thirty seconds before a patient walks in.
_RECENT_ENCOUNTERS = 3
_RECENT_RESULTS = 5
_LOOKBACK_DAYS = 180


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _encounter_summary(encounter: Encounter) -> Dict[str, Any]:
    return {
        "id": encounter.id,
        "started_at": encounter.started_at.isoformat(),
        "status": encounter.status,
        "specialty": encounter.specialty,
        "chief_complaint": encounter.chief_complaint or "",
        "assessment": encounter.assessment or "",
        "plan": encounter.plan or "",
        "vitals": format_vitals(encounter.vitals or {}),
    }


async def build_pre_visit_brief(
    session: AsyncSession, patient: Patient, *, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """Everything already known about this patient, in one read.

    Ordered by what a clinician looks at first: why they are here, what is
    unresolved, what came back since the last visit, and what they are taking.
    """
    moment = now or _now()
    since = moment - timedelta(days=_LOOKBACK_DAYS)

    next_appointment = (
        await session.scalars(
            select(Appointment)
            .where(
                Appointment.patient_id == patient.id,
                Appointment.status == "booked",
                Appointment.end_at >= moment,
            )
            .order_by(Appointment.start_at)
            .limit(1)
        )
    ).first()

    recent_encounters = (
        await session.scalars(
            select(Encounter)
            .where(Encounter.patient_id == patient.id, Encounter.status != "draft")
            .order_by(Encounter.started_at.desc())
            .limit(_RECENT_ENCOUNTERS)
        )
    ).all()

    open_tasks = (
        await session.scalars(
            select(Task)
            .where(Task.patient_id == patient.id, Task.status.in_(svc.OPEN_STATUSES))
            .order_by(Task.due_at.is_(None), Task.due_at.asc())
            .limit(20)
        )
    ).all()

    active_alerts = (
        await session.scalars(
            select(Alert)
            .where(Alert.patient_id == patient.id, Alert.status != "resolved")
            .order_by(Alert.created_at.desc())
            .limit(10)
        )
    ).all()

    labs = (
        await session.scalars(
            select(LabResult)
            .where(LabResult.patient_id == patient.id, LabResult.taken_at >= since)
            .order_by(LabResult.taken_at.desc())
            .limit(_RECENT_RESULTS)
        )
    ).all()

    imaging = (
        await session.scalars(
            select(ImagingStudy)
            .where(ImagingStudy.patient_id == patient.id, ImagingStudy.study_date >= since.date())
            .order_by(ImagingStudy.study_date.desc())
            .limit(_RECENT_RESULTS)
        )
    ).all()

    # The same read-time rules the patient page uses (decision #10), so the
    # brief and the chart cannot disagree about whether something is a risk.
    risk_flags = assess_patient_risk(patient.lab_results, patient.medications, patient.allergies)

    return {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "age": patient.age,
            "sex": patient.sex,
            "medical_record_number": patient.medical_record_number,
        },
        "reason": next_appointment.reason if next_appointment else "",
        "next_appointment": (
            {
                "id": next_appointment.id,
                "start_at": next_appointment.start_at.isoformat(),
                "mode": next_appointment.mode,
                "confirmed": next_appointment.confirmed_at is not None,
            }
            if next_appointment
            else None
        ),
        "recent_encounters": [_encounter_summary(e) for e in recent_encounters],
        "open_tasks": [
            {
                "id": t.id,
                "title": t.title,
                "category": t.category,
                "severity": t.severity,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "overdue": bool(t.due_at and t.due_at < moment),
            }
            for t in open_tasks
        ],
        "alerts": [
            {
                "id": a.id,
                "title": a.title,
                "severity": a.severity,
                "kind": a.kind,
                "status": a.status,
            }
            for a in active_alerts
        ],
        "recent_results": [
            {
                "kind": "lab",
                "name": lab.test_name,
                "value": f"{lab.value} {lab.unit}".strip(),
                "date": lab.taken_at.isoformat(),
                "abnormal": bool(lab.is_abnormal or lab.is_critical),
                "critical": bool(lab.is_critical),
            }
            for lab in labs
        ]
        + [
            {
                "kind": "imaging",
                "name": f"{study.modality} {study.body_part}".strip(),
                "value": study.severity,
                "date": study.study_date.isoformat(),
                "abnormal": study.severity in ("critical", "review"),
                "critical": study.severity == "critical",
            }
            for study in imaging
        ],
        "medications": list(patient.medications or []),
        "allergies": list(patient.allergies or []),
        "conditions": list(patient.conditions or []),
        "risk_flags": [
            {
                "rule_key": flag.get("rule_key", ""),
                "label": flag["label"],
                "severity": flag["severity"],
                "detail": flag["detail"],
            }
            for flag in risk_flags
        ],
    }


__all__ = ["build_pre_visit_brief"]
