"""Patient portal — identity/chart reads only.

Every handler derives the patient from `current_patient_record` (the
token), never from a path or query parameter — there is no `patient_id`
anywhere in this router to tamper with. Scheduling and exam-results
sharing (a separate feature) live in their own routers and mix both
roles per-route rather than funneling through here; this router is
reserved for "my own chart" reads.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import log_phi_access
from auth.deps import current_patient_record, require_patient
from core.db import get_session
from data.schemas import Patient, TimelineEvent, User

router = APIRouter()


def _event(event: TimelineEvent) -> Dict[str, Any]:
    return {
        "date": event.date.isoformat(),
        "type": event.type,
        "title": event.title,
        "detail": event.detail,
        "ai_generated": event.ai_generated,
    }


def _portal_view(patient: Patient) -> Dict[str, Any]:
    """Deliberately not `patients.py::_full` — `risk_level`/`risk_flags`
    are clinician-facing, rule-derived artifacts that should not be
    surfaced to a patient uninterpreted. Timeline is filtered to
    non-AI-generated events unless a clinician has explicitly shared one
    (see the results-sharing feature)."""
    return {
        "id": patient.id,
        "name": patient.name,
        "age": patient.age,
        "sex": patient.sex,
        "conditions": patient.conditions,
        "medications": patient.medications,
        "allergies": patient.allergies,
    }


@router.get("/me")
async def portal_me(
    patient: Patient = Depends(current_patient_record),
    user: User = Depends(require_patient),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    await log_phi_access(session, user, patient.id, "/api/portal/me", "GET")
    return _portal_view(patient)


@router.get("/timeline")
async def portal_timeline(
    patient: Patient = Depends(current_patient_record),
    user: User = Depends(require_patient),
    session: AsyncSession = Depends(get_session),
    event_type: Optional[str] = None,
) -> Dict[str, Any]:
    await log_phi_access(session, user, patient.id, "/api/portal/timeline", "GET")
    events: List[TimelineEvent] = [e for e in patient.timeline if not e.ai_generated]
    if event_type:
        events = [e for e in events if e.type == event_type]
    return {"patient_id": patient.id, "events": [_event(e) for e in events]}


@router.get("/labs")
async def portal_labs(
    patient: Patient = Depends(current_patient_record),
    user: User = Depends(require_patient),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    await log_phi_access(session, user, patient.id, "/api/portal/labs", "GET")
    return {"patient_id": patient.id, "lab_results": patient.lab_results}
