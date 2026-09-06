"""The visit, over HTTP.

One verb per transition rather than a `PATCH {status}`, same reasoning as
`tasks.py`: signing and amending have different guards and different
consequences, and a generic status write hides both.

`POST /{id}/draft-note` is the only endpoint here that reaches a model, and it
is deliberately a *read*: it returns a draft and writes nothing. The clinician
applies it with a `PATCH` if they want it, so a model's text never sits in a
patient's record before a human has looked at it (ADR-016).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import require_clinician
from core.config import settings
from core.db import get_session
from data.schemas import Appointment, Encounter, EncounterOrder, Patient, User
from sephiroth.clinical.templates import SPECIALTIES, encounter_template
from sephiroth.clinical.vitals import VITAL_SPECS, VitalError, vital_findings

from ..audit import add_phi_access
from ..services import encounter_service as svc
from ..services.encounter_drafting import draft_encounter_note

router = APIRouter(dependencies=[Depends(require_clinician)])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CreateEncounterRequest(BaseModel):
    patient_id: str
    appointment_id: Optional[str] = None
    specialty: str = "general"
    chief_complaint: str = ""


class UpdateEncounterRequest(BaseModel):
    """Every field optional: a `PATCH` writes only what it names.

    `None` means "not sent" and is dropped, so clearing a section is done by
    sending an empty string. Without that distinction a form that omits a field
    would silently erase it.
    """

    chief_complaint: Optional[str] = None
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None
    patient_instructions: Optional[str] = None
    specialty: Optional[str] = None
    vitals: Optional[Dict[str, Any]] = None
    note_source: Optional[str] = Field(None, pattern="^(clinician|llm|template)$")
    note_model: Optional[str] = None


class OrderRequest(BaseModel):
    kind: str = Field(pattern="^(lab|imaging|referral|followup|medication)$")
    detail: str = Field(min_length=1, max_length=500)
    due_in_days: Optional[int] = Field(None, gt=0, le=365)


class DraftNoteRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=20000)
    specialty: Optional[str] = None


class AmendRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


def _order_out(order: EncounterOrder) -> Dict[str, Any]:
    return {
        "id": order.id,
        "kind": order.kind,
        "detail": order.detail,
        "due_in_days": order.due_in_days,
        "task_id": order.task_id,
    }


def _encounter_out(
    encounter: Encounter,
    orders: Sequence[EncounterOrder] = (),
    *,
    patient_name: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": encounter.id,
        "patient_id": encounter.patient_id,
        "patient_name": patient_name,
        "clinician_id": encounter.clinician_id,
        "appointment_id": encounter.appointment_id,
        "specialty": encounter.specialty,
        "status": encounter.status,
        "chief_complaint": encounter.chief_complaint,
        "vitals": encounter.vitals or {},
        # Computed on read, never stored: a flag written at save time would
        # still say "normal" after the ranges were corrected.
        "vital_findings": [
            {
                "key": f.key,
                "label": f.label,
                "display": f.display,
                "severity": f.severity,
                "detail": f.detail,
            }
            for f in vital_findings(encounter.vitals or {})
        ],
        "subjective": encounter.subjective,
        "objective": encounter.objective,
        "assessment": encounter.assessment,
        "plan": encounter.plan,
        "patient_instructions": encounter.patient_instructions,
        "note_source": encounter.note_source,
        "note_model": encounter.note_model,
        "editable": svc.is_editable(encounter),
        "signable": svc.is_editable(encounter) and svc.has_content(encounter),
        "started_at": encounter.started_at.isoformat(),
        "signed_at": encounter.signed_at.isoformat() if encounter.signed_at else None,
        "signed_by": encounter.signed_by,
        "amended_at": encounter.amended_at.isoformat() if encounter.amended_at else None,
        "amendment_reason": encounter.amendment_reason,
        "clinical_note_id": encounter.clinical_note_id,
        "orders": [_order_out(o) for o in orders],
        "template": encounter_template(encounter.specialty).as_dict(),
    }


async def _get(session: AsyncSession, encounter_id: str) -> Encounter:
    encounter = await svc.get_encounter(session, encounter_id)
    if encounter is None:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return encounter


async def _patient_name(session: AsyncSession, patient_id: str) -> Optional[str]:
    patient = await session.get(Patient, patient_id)
    return patient.name if patient else None


def _guard(action) -> Any:
    """Map the service's refusal onto 409 in one place."""
    try:
        return action()
    except svc.EncounterTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VitalError as exc:
        # A value no body produces is a bad request, not a bad state.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/vitals/spec", summary="The vitals this product records, with their ranges")
async def vitals_spec() -> Dict[str, Any]:
    """Served rather than duplicated in the frontend: a range the UI validates
    against and a range the API enforces must be the same range."""
    return {
        "vitals": [
            {
                "key": spec.key,
                "label": spec.label,
                "unit": spec.unit,
                "min": spec.physiological[0],
                "max": spec.physiological[1],
                "normal_low": spec.clinical[0],
                "normal_high": spec.clinical[1],
                "decimals": spec.decimals,
            }
            for spec in VITAL_SPECS.values()
        ],
        "specialties": list(SPECIALTIES),
    }


@router.post("", summary="Start an encounter")
async def create_encounter(
    body: CreateEncounterRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    patient = await session.get(Patient, body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    if body.appointment_id:
        appointment = await session.get(Appointment, body.appointment_id)
        if appointment is None or appointment.patient_id != patient.id:
            raise HTTPException(status_code=404, detail="Appointment not found for this patient")
        existing = await svc.list_encounters(session, patient_id=patient.id)
        if any(e.appointment_id == body.appointment_id for e in existing):
            # Caught here as well as by the unique index, so the clinician gets
            # a sentence instead of an integrity error.
            raise HTTPException(status_code=409, detail="This appointment already has an encounter")

    encounter = await svc.create_encounter(
        session,
        patient_id=patient.id,
        clinician=clinician,
        appointment_id=body.appointment_id,
        specialty=body.specialty,
        chief_complaint=body.chief_complaint,
        now=_now(),
    )
    add_phi_access(session, clinician.id, patient.id, "/api/encounters", "POST")
    await session.commit()
    return _encounter_out(encounter, [], patient_name=patient.name)


@router.get("", summary="Encounters, newest first")
async def list_encounters(
    patient_id: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(draft|signed|amended)$"),
    mine: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    encounters = await svc.list_encounters(
        session,
        patient_id=patient_id,
        clinician_id=clinician.id if mine else None,
        status=status,
        limit=limit,
        offset=offset,
    )
    for encounter in encounters:
        add_phi_access(session, clinician.id, encounter.patient_id, "/api/encounters", "GET")
    names = {e.patient_id: await _patient_name(session, e.patient_id) for e in encounters}
    orders = {e.id: await svc.list_orders(session, e) for e in encounters}
    await session.commit()
    return {
        "items": [_encounter_out(e, orders[e.id], patient_name=names.get(e.patient_id)) for e in encounters]
    }


@router.get("/{encounter_id}", summary="One encounter with its orders")
async def get_encounter(
    encounter_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    encounter = await _get(session, encounter_id)
    add_phi_access(session, clinician.id, encounter.patient_id, f"/api/encounters/{encounter_id}", "GET")
    name = await _patient_name(session, encounter.patient_id)
    orders = await svc.list_orders(session, encounter)
    await session.commit()
    return _encounter_out(encounter, orders, patient_name=name)


@router.patch("/{encounter_id}", summary="Edit a draft")
async def update_encounter(
    encounter_id: str,
    body: UpdateEncounterRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    encounter = await _get(session, encounter_id)
    changes = body.model_dump(exclude_none=True)
    orders = await svc.list_orders(session, encounter)
    if not changes:
        return _encounter_out(encounter, orders)

    _guard(lambda: svc.update_encounter(encounter, changes, now=_now()))
    add_phi_access(session, clinician.id, encounter.patient_id, f"/api/encounters/{encounter_id}", "PATCH")
    await session.commit()
    return _encounter_out(encounter, orders)


@router.post("/{encounter_id}/orders", summary="Add an order")
async def add_order(
    encounter_id: str,
    body: OrderRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    encounter = await _get(session, encounter_id)
    try:
        await svc.add_order(
            session,
            encounter,
            kind=body.kind,
            detail=body.detail,
            due_in_days=body.due_in_days,
            now=_now(),
        )
    except svc.EncounterTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _encounter_out(encounter, await svc.list_orders(session, encounter))


@router.delete("/{encounter_id}/orders/{order_id}", summary="Remove an order from a draft")
async def remove_order(
    encounter_id: str,
    order_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    encounter = await _get(session, encounter_id)
    orders = await svc.list_orders(session, encounter)
    order = next((o for o in orders if o.id == order_id), None)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found on this encounter")
    try:
        await svc.remove_order(session, encounter, order)
    except svc.EncounterTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _encounter_out(encounter, await svc.list_orders(session, encounter))


@router.post("/{encounter_id}/draft-note", summary="Ask the model to structure free text")
async def draft_note(
    encounter_id: str,
    body: DraftNoteRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Returns a draft and **persists nothing** (B-10).

    Always returns something usable: with no model, or with PHI egress
    forbidden, the response carries the clinician's own text under the right
    headings and says so in `source`.
    """
    encounter = await _get(session, encounter_id)
    if not svc.is_editable(encounter):
        raise HTTPException(status_code=409, detail="a signed encounter cannot be redrafted")

    draft = await draft_encounter_note(body.transcript, body.specialty or encounter.specialty)
    add_phi_access(
        session,
        clinician.id,
        encounter.patient_id,
        f"/api/encounters/{encounter_id}/draft-note",
        "POST",
    )
    await session.commit()
    return draft


@router.post("/{encounter_id}/sign", summary="Commit the visit")
async def sign_encounter(
    encounter_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Writes the note into the chart and files one task per order.

    Idempotent: a second sign changes nothing and creates nothing, so a
    double-click cannot put two notes in a chart.
    """
    encounter = await _get(session, encounter_id)
    try:
        _encounter, task_ids = await svc.sign_encounter(session, encounter, signer=clinician, now=_now())
    except svc.EncounterTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    orders = await svc.list_orders(session, encounter)
    await session.commit()
    return {**_encounter_out(encounter, orders), "tasks_created": task_ids}


@router.post("/{encounter_id}/amend", summary="Reopen a signed encounter with a reason")
async def amend_encounter(
    encounter_id: str,
    body: AmendRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    encounter = await _get(session, encounter_id)
    try:
        await svc.amend_encounter(
            session,
            encounter,
            actor=clinician,
            reason=body.reason,
            window_days=settings.encounter_amend_window_days,
            now=_now(),
        )
    except svc.EncounterTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _encounter_out(encounter, await svc.list_orders(session, encounter))


__all__ = ["router"]
