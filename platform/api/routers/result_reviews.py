"""The results inbox: what arrived, who read it, what they decided.

Mounted beside the existing `/api/results/*` sharing endpoints rather than
inside them. Those serve the patient portal and have their own role rules —
both a clinician and a patient legitimately call most of them — while
everything here is clinician-only, and mixing the two guard styles in one
router is how a route ends up protected by accident.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import require_clinician
from core.config import settings
from core.db import get_session
from data.schemas import Patient, ResultReview, TimelineEvent, User

from ..audit import add_phi_access
from ..services import result_service as svc
from ..timeparse import optional_aware

router = APIRouter(dependencies=[Depends(require_clinician)])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LabIntake(BaseModel):
    patient_id: str
    test_name: str = Field(min_length=1, max_length=60)
    value: float
    unit: str = Field("", max_length=20)
    taken_at: Optional[datetime] = None
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None


class ImagingIntake(BaseModel):
    patient_id: str
    modality: str = Field(min_length=1, max_length=20)
    body_part: str = Field(min_length=1, max_length=60)
    study_date: Optional[date] = None
    severity: str = Field("none", pattern="^(critical|review|none)$")
    finding_summary: str = ""
    is_new_finding: bool = False


class ReviewRequest(BaseModel):
    disposition: str = Field(pattern="^(normal|abnormal_expected|action_taken|needs_patient_contact)$")
    note: str = Field("", max_length=2000)


class CommunicateRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    #: The timeline entry the portal renders. Required rather than derived: a
    #: result and its narrative entry are separate rows, and guessing which
    #: entry belongs to which result is how a patient sees the wrong one.
    timeline_event_id: int


def _review_out(review: ResultReview, result: Any, *, patient_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": review.id,
        "result_type": review.result_type,
        "result_id": review.result_id,
        "patient_id": review.patient_id,
        "patient_name": patient_name,
        "status": review.status,
        "severity": review.severity,
        "classification_reason": review.classification_reason,
        "disposition": review.disposition,
        "note": review.note,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "reviewed_by": review.reviewed_by,
        "share_id": review.share_id,
        "task_id": review.task_id,
        "closed_at": review.closed_at.isoformat() if review.closed_at else None,
        "created_at": review.created_at.isoformat(),
        # What the UI needs to know before offering a button, so a refusal is
        # never a surprise 409.
        "needs_communication": review.disposition == svc.NEEDS_CONTACT and review.status != "communicated",
        "closable": review.status in ("reviewed", "communicated")
        and not (review.disposition == svc.NEEDS_CONTACT and review.status != "communicated"),
        "result": svc.result_out(result, review),
    }


async def _get(session: AsyncSession, review_id: str) -> ResultReview:
    review = await svc.get_review(session, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Result review not found")
    return review


async def _patient_name(session: AsyncSession, patient_id: str) -> Optional[str]:
    patient = await session.get(Patient, patient_id)
    return patient.name if patient else None


async def _out(session: AsyncSession, review: ResultReview) -> Dict[str, Any]:
    result = await svc.load_result(session, review)
    return _review_out(review, result, patient_name=await _patient_name(session, review.patient_id))


@router.post("/labs", status_code=201, summary="Record a lab result")
async def record_lab(
    body: LabIntake,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Idempotent on `(patient, test, taken_at)`: the same measurement arriving
    twice is the same measurement."""
    if await session.get(Patient, body.patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    _result, review, created = await svc.record_lab_result(
        session,
        patient_id=body.patient_id,
        test_name=body.test_name,
        value=body.value,
        unit=body.unit,
        # A lab draw time without an offset is ambiguous, and this one is the
        # idempotency key: two feeds disagreeing by five hours about the same
        # draw would produce two results and two inbox rows (SPEC-027 B-1).
        taken_at=optional_aware(body.taken_at, "taken_at"),
        reference_low=body.reference_low,
        reference_high=body.reference_high,
        now=_now(),
    )
    add_phi_access(session, clinician.id, body.patient_id, "/api/results/labs", "POST")
    await session.commit()
    return {**await _out(session, review), "created": created}


@router.post("/imaging", status_code=201, summary="Record an imaging study")
async def record_imaging(
    body: ImagingIntake,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    if await session.get(Patient, body.patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    _study, review, created = await svc.record_imaging_study(
        session,
        patient_id=body.patient_id,
        modality=body.modality,
        body_part=body.body_part,
        study_date=body.study_date,
        severity=body.severity,
        finding_summary=body.finding_summary,
        is_new_finding=body.is_new_finding,
        now=_now(),
    )
    add_phi_access(session, clinician.id, body.patient_id, "/api/results/imaging", "POST")
    await session.commit()
    return {**await _out(session, review), "created": created}


@router.get("/inbox", summary="Results waiting on somebody")
async def inbox(
    status: List[str] = Query(default=list(svc.OPEN_STATUSES)),
    severity: Optional[str] = Query(None, pattern="^(critical|abnormal|normal|unclassified)$"),
    patient_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    reviews = await svc.list_reviews(
        session,
        status=status,
        severity=severity,
        patient_id=patient_id,
        limit=limit,
        offset=offset,
    )
    items = []
    for review in reviews:
        add_phi_access(session, clinician.id, review.patient_id, "/api/results/inbox", "GET")
        items.append(await _out(session, review))
    await session.commit()
    return {"items": items}


@router.get("/reviews/{review_id}", summary="One result and what was decided about it")
async def get_review(
    review_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    review = await _get(session, review_id)
    add_phi_access(session, clinician.id, review.patient_id, f"/api/results/reviews/{review_id}", "GET")
    body = await _out(session, review)
    await session.commit()
    return body


@router.post("/reviews/{review_id}/review", summary="Record the decision")
async def review_result(
    review_id: str,
    body: ReviewRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    review = await _get(session, review_id)
    try:
        await svc.review_result(
            session,
            review,
            actor=clinician,
            disposition=body.disposition,
            note=body.note,
            now=_now(),
        )
    except svc.ResultTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return await _out(session, review)


@router.post("/reviews/{review_id}/communicate", summary="Tell the patient")
async def communicate(
    review_id: str,
    body: CommunicateRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    review = await _get(session, review_id)

    event = await session.get(TimelineEvent, body.timeline_event_id)
    if event is None or event.patient_id != review.patient_id:
        # The same check `results.py` makes when sharing: an event belonging to
        # someone else would show one patient another patient's result.
        raise HTTPException(status_code=404, detail="Timeline entry not found for this patient")

    try:
        await svc.communicate_result(
            session,
            review,
            actor=clinician,
            message=body.message,
            timeline_event_id=body.timeline_event_id,
            now=_now(),
        )
    except svc.ResultTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return await _out(session, review)


@router.post("/reviews/{review_id}/close", summary="Close the loop")
async def close(
    review_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Refused while a result marked as needing patient contact has not been
    communicated. That guard is the phase."""
    review = await _get(session, review_id)
    try:
        await svc.close_result(session, review, actor=clinician, now=_now())
    except svc.ResultTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return await _out(session, review)


@router.post("/reviews/{review_id}/reopen", summary="Undo a close")
async def reopen(
    review_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    review = await _get(session, review_id)
    try:
        await svc.reopen_result(
            session,
            review,
            actor=clinician,
            window_days=settings.result_reopen_window_days,
            now=_now(),
        )
    except svc.ResultTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return await _out(session, review)


__all__ = ["router"]
