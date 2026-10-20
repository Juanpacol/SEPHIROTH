"""The results inbox: what arrived, who read it, what they decided.

Mounted beside the existing `/api/results/*` sharing endpoints rather than
inside them. Those serve the patient portal and have their own role rules —
both a clinician and a patient legitimately call most of them — while
everything here is clinician-only, and mixing the two guard styles in one
router is how a route ends up protected by accident.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import add_phi_access
from api.services import result_service as svc
from api.timeparse import optional_aware
from auth.deps import require_clinician
from core.config import settings
from core.db import get_session
from data.schemas import Notification, Patient, ResultReview, ResultShare, TimelineEvent, User
from sephiroth.clinical.results import classify_lab, implausible_reason, lab_catalog
from sephiroth.workflows import events as workflow_events

router = APIRouter(dependencies=[Depends(require_clinician)])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class _LabValue(BaseModel):
    """A lab value as typed. Refused as a typo when no real measurement could be
    it (a slipped decimal, a negative), before anything is stored or classified."""

    test_name: str = Field(min_length=1, max_length=60)
    value: float
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None

    @model_validator(mode="after")
    def _plausible(self) -> "_LabValue":
        reason = implausible_reason(self.test_name, self.value)
        if reason:
            raise ValueError(reason)
        return self


class LabIntake(_LabValue):
    patient_id: str
    unit: str = Field("", max_length=20)
    taken_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _not_in_the_future(self) -> "LabIntake":
        # A draw cannot have happened yet. A few minutes of slack for clocks that
        # disagree; a naive time is left for `optional_aware` to refuse, as before.
        if self.taken_at is not None and self.taken_at.tzinfo is not None:
            if self.taken_at.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError("taken_at cannot be in the future.")
        return self


class LabPreview(_LabValue):
    """What the form asks before saving: how would this value be classified?"""


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
    #: The timeline entry the portal renders. Optional: leave it out and one is
    #: made from the result itself (a lab is not a timeline entry, so a result
    #: recorded on its own has none to point at). Send one to attach the
    #: patient's own existing entry instead.
    timeline_event_id: Optional[int] = None


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


@router.get("/labs/catalog", summary="The lab tests the form offers, with unit and reference range")
async def lab_tests() -> Dict[str, Any]:
    return {"tests": lab_catalog()}


@router.post("/labs/preview", summary="How a lab value would be classified, without saving it")
async def preview_lab(body: LabPreview) -> Dict[str, Any]:
    """The same rules that classify a result when it is recorded, run on what the
    form has so far, so the clinician sees the outcome before saving. Nothing is
    written."""
    result = classify_lab(
        body.test_name, body.value, reference_low=body.reference_low, reference_high=body.reference_high
    )
    return {
        "severity": result.severity,
        "reason": result.reason,
        "reference_low": result.reference_low,
        "reference_high": result.reference_high,
    }


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


def _timeline_entry_for(review: ResultReview, result: Any) -> TimelineEvent:
    """The entry the portal renders for a result that has none of its own.
    Title only: the value and the unit, nothing the clinician did not record."""
    if review.result_type == "lab" and result is not None:
        name = result.test_name.replace("_", " ").strip()
        value = f"{result.value:g}" + (f" {result.unit}" if result.unit else "")
        return TimelineEvent(
            patient_id=review.patient_id,
            date=result.taken_at.date(),
            type="lab",
            title=f"{name[:1].upper()}{name[1:]}: {value}"[:200],
        )
    modality = (getattr(result, "modality", "") or "").upper()
    part = getattr(result, "body_part", "") or ""
    return TimelineEvent(
        patient_id=review.patient_id,
        date=getattr(result, "study_date", None) or _now().date(),
        type="imaging",
        title=f"{modality} {part}".strip()[:200] or "Imaging result",
    )


@router.post("/reviews/{review_id}/communicate", summary="Tell the patient")
async def communicate(
    review_id: str,
    body: CommunicateRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Tell the patient, record it, and notify them.

    One transaction: the share, the notification and the workflow event land
    together or not at all. A result is told once -- a second attempt is a 409,
    so a double click never sends two messages or two notifications.
    """
    review = await _get(session, review_id)

    if body.timeline_event_id is not None:
        event = await session.get(TimelineEvent, body.timeline_event_id)
        if event is None or event.patient_id != review.patient_id:
            # The same check `results.py` makes when sharing: an event belonging
            # to someone else would show one patient another patient's result.
            raise HTTPException(status_code=404, detail="Timeline entry not found for this patient")
        already = await session.scalar(
            select(ResultShare.id).where(
                ResultShare.timeline_event_id == event.id, ResultShare.patient_id == review.patient_id
            )
        )
        if already is not None:
            raise HTTPException(status_code=409, detail="That timeline entry has already been shared")
    else:
        # Checked here too, before a timeline entry is made for nothing.
        if review.share_id is not None:
            raise HTTPException(status_code=409, detail="This result has already been communicated")
        if review.status not in ("reviewed", "communicated"):
            raise HTTPException(
                status_code=409, detail="a result has to be reviewed before it is communicated"
            )
        event = _timeline_entry_for(review, await svc.load_result(session, review))
        session.add(event)
        await session.flush()

    try:
        share = await svc.communicate_result(
            session,
            review,
            actor=clinician,
            message=body.message,
            timeline_event_id=event.id,
            now=_now(),
        )
    except svc.ResultTransitionError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if review.result_type == "lab":
        workflow_events.emit(
            session,
            workflow_events.LAB_RESULT_AVAILABLE,
            "result_share",
            share.id,
            patient_id=review.patient_id,
        )
    patient_login = await session.scalar(select(User).where(User.patient_id == review.patient_id))
    if patient_login is not None:
        session.add(
            Notification(
                id=str(uuid4()),
                user_id=patient_login.id,
                type="result_shared",
                message="A new result has been shared with you.",
            )
        )
    add_phi_access(
        session, clinician.id, review.patient_id, f"/api/results/reviews/{review.id}/communicate", "POST"
    )
    await session.commit()
    return {**await _out(session, review), "patient_notified": patient_login is not None}


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
