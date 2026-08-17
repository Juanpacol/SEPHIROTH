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

from auth.deps import current_patient_record
from data.schemas import Patient, TimelineEvent

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
async def portal_me(patient: Patient = Depends(current_patient_record)) -> Dict[str, Any]:
    return _portal_view(patient)


@router.get("/timeline")
async def portal_timeline(
    patient: Patient = Depends(current_patient_record),
    event_type: Optional[str] = None,
) -> Dict[str, Any]:
    events: List[TimelineEvent] = [e for e in patient.timeline if not e.ai_generated]
    if event_type:
        events = [e for e in events if e.type == event_type]
    return {"patient_id": patient.id, "events": [_event(e) for e in events]}


@router.get("/labs")
async def portal_labs(patient: Patient = Depends(current_patient_record)) -> Dict[str, Any]:
    return {"patient_id": patient.id, "lab_results": patient.lab_results}
