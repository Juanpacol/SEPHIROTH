"""Recording a result, and closing the loop on it.

Two halves.

**Intake** writes the result row and its review in one transaction, so a result
can never exist without a lifecycle — the invariant ADR-017 moved out of the
schema and into here, which is why it has its own test. It is idempotent on
`(patient, test, taken_at)`: a feed that retries must not put two potassiums in
front of a clinician.

**The loop** is received → reviewed → communicated → closed, and its one
load-bearing guard is that a result whose disposition was "tell the patient"
cannot be closed until they have been told. Without that the states are
decoration.

Transaction discipline: **nothing here commits.** The routers do.

Restoration note: filing a task for a result worth attention, and completing
that task when the review closes, used to go through `task_service`
(SPEC-018's unified inbox). That system was removed in the c7fbdf5 revert and
is a later restoration phase — `_file_task` below is a deliberate no-op stub
until it comes back, same posture as `encounter_service._file_orders`.
`close_result` no longer has a task to complete, so that half of the old
behavior is simply absent rather than stubbed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import ImagingStudy, LabResult, Patient, ResultReview, ResultShare, User
from sephiroth.clinical.results import (
    Classification,
    classify_imaging,
    classify_lab,
    deserves_a_task,
)

OPEN_STATUSES = ("received", "reviewed", "communicated")

#: What the clinician decided. `normal` is the only one that needs no
#: justification -- see `review` for why requiring one would be worse.
DISPOSITIONS = ("normal", "abnormal_expected", "action_taken", "needs_patient_contact")

#: The disposition that keeps the loop open until the patient is told.
NEEDS_CONTACT = "needs_patient_contact"


class ResultTransitionError(RuntimeError):
    """A transition the review's current state forbids. Surfaces as 409."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _file_task(
    session: AsyncSession,
    review: ResultReview,
    *,
    label: str,
    detail: str,
    now: datetime,
) -> Optional[str]:
    """Would file one task per result worth attention via the unified task
    inbox (SPEC-018). Deliberate no-op for now (see this module's docstring):
    the review is still classified and listed by severity regardless, so a
    clinician scanning the inbox sees it either way -- what's missing is only
    the separate task-list entry until that system is restored.
    """
    return None


async def _create_review(
    session: AsyncSession,
    *,
    result_type: str,
    result_id: str,
    patient_id: str,
    classification: Classification,
    now: datetime,
) -> ResultReview:
    review = ResultReview(
        id=str(uuid4()),
        result_type=result_type,
        result_id=str(result_id),
        patient_id=patient_id,
        status="received",
        severity=classification.severity,
        classification_reason=classification.reason[:300],
        created_at=now,
        updated_at=now,
    )
    session.add(review)
    await session.flush()
    return review


async def get_review(session: AsyncSession, review_id: str) -> Optional[ResultReview]:
    return await session.get(ResultReview, review_id)


async def review_for_result(
    session: AsyncSession, result_type: str, result_id: str
) -> Optional[ResultReview]:
    return (
        await session.scalars(
            select(ResultReview).where(
                ResultReview.result_type == result_type,
                ResultReview.result_id == str(result_id),
            )
        )
    ).first()


# --------------------------------------------------------------------------
# Intake
# --------------------------------------------------------------------------


async def _existing_lab(
    session: AsyncSession, patient_id: str, test_name: str, taken_at: datetime
) -> Optional[LabResult]:
    return (
        await session.scalars(
            select(LabResult).where(
                LabResult.patient_id == patient_id,
                LabResult.test_name == test_name,
                LabResult.taken_at == taken_at,
            )
        )
    ).first()


async def record_lab_result(
    session: AsyncSession,
    *,
    patient_id: str,
    test_name: str,
    value: float,
    unit: str = "",
    taken_at: Optional[datetime] = None,
    reference_low: Optional[float] = None,
    reference_high: Optional[float] = None,
    now: Optional[datetime] = None,
) -> Tuple[LabResult, ResultReview, bool]:
    """Record one lab measurement. Returns `(result, review, created)`.

    Idempotent on `(patient, test, taken_at)`: the same measurement arriving
    twice is the same measurement, and a retrying feed must not double the
    inbox.
    """
    moment = now or _now()
    measured_at = taken_at or moment

    existing = await _existing_lab(session, patient_id, test_name, measured_at)
    if existing is not None:
        review = await review_for_result(session, "lab", existing.id)
        if review is not None:
            return existing, review, False

    classification = classify_lab(
        test_name, value, reference_low=reference_low, reference_high=reference_high
    )

    result = existing or LabResult(
        patient_id=patient_id,
        test_name=test_name,
        value=value,
        unit=unit,
        taken_at=measured_at,
        created_at=moment,
    )
    result.reference_low = classification.reference_low
    result.reference_high = classification.reference_high
    result.is_abnormal = classification.is_abnormal
    result.is_critical = classification.is_critical
    session.add(result)
    # Flushed here because `LabResult.id` is autoincrementing and the review
    # keys on it -- there is no id to point at until the insert happens.
    await session.flush()

    review = await _create_review(
        session,
        result_type="lab",
        result_id=str(result.id),
        patient_id=patient_id,
        classification=classification,
        now=moment,
    )

    if deserves_a_task(classification):
        await _file_task(
            session,
            review,
            label=f"{test_name} {value} {unit}".strip(),
            detail=classification.reason,
            now=moment,
        )

    await _update_patient_panel(session, patient_id, test_name, value)
    return result, review, True


async def _update_patient_panel(session: AsyncSession, patient_id: str, test_name: str, value: float) -> None:
    """Keep `Patient.lab_results` in step with the row just recorded.

    Two representations of one lab value exist -- the JSON panel the risk engine
    reads and the `LabResult` table everything else reads -- and they have been
    free to disagree because nothing wrote both. This is the narrow fix
    (SPEC-024 §11 risk 2): new results write both, so they agree going forward.
    Unifying them means rewriting the risk engine's read path and inventing
    timestamps the panel never had.
    """
    patient = await session.get(Patient, patient_id)
    if patient is None:
        return
    from sephiroth.clinical.results import _normalise

    panel = dict(patient.lab_results or {})
    panel[_normalise(test_name)] = str(value)
    patient.lab_results = panel


async def record_imaging_study(
    session: AsyncSession,
    *,
    patient_id: str,
    modality: str,
    body_part: str,
    study_date: Optional[date] = None,
    severity: str = "none",
    finding_summary: str = "",
    is_new_finding: bool = False,
    now: Optional[datetime] = None,
) -> Tuple[ImagingStudy, ResultReview, bool]:
    moment = now or _now()
    classification = classify_imaging(severity, finding_summary)

    study = ImagingStudy(
        id=str(uuid4()),
        patient_id=patient_id,
        modality=modality,
        body_part=body_part,
        study_date=study_date or moment.date(),
        status="analyzed" if finding_summary else "pending",
        finding_summary=finding_summary or None,
        severity=severity,
        is_new_finding=is_new_finding,
        analyzed_at=moment if finding_summary else None,
        created_at=moment,
    )
    session.add(study)
    await session.flush()

    review = await _create_review(
        session,
        result_type="imaging",
        result_id=study.id,
        patient_id=patient_id,
        classification=classification,
        now=moment,
    )

    if deserves_a_task(classification):
        await _file_task(
            session,
            review,
            label=f"{modality} {body_part}".strip(),
            detail=classification.reason,
            now=moment,
        )
    return study, review, True


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------


async def review_result(
    session: AsyncSession,
    review: ResultReview,
    *,
    actor: User,
    disposition: str,
    note: str = "",
    now: Optional[datetime] = None,
) -> ResultReview:
    """Record what the clinician decided.

    A note is required for every disposition except `normal`. Requiring one
    there too would teach people to type "ok", and an inbox full of "ok" looks
    like review without being it (SPEC-024 §11 risk 5).
    """
    if review.status not in ("received", "reviewed"):
        raise ResultTransitionError("this result has already moved past review")
    if disposition not in DISPOSITIONS:
        raise ResultTransitionError(f"unknown disposition: {disposition}")
    if disposition != "normal" and not (note or "").strip():
        raise ResultTransitionError("a decision other than 'normal' needs a note saying why")

    moment = now or _now()
    review.status = "reviewed"
    review.disposition = disposition
    review.note = (note or "").strip()
    review.reviewed_at = moment
    review.reviewed_by = actor.id
    review.updated_at = moment
    return review


async def communicate_result(
    session: AsyncSession,
    review: ResultReview,
    *,
    actor: User,
    message: str,
    timeline_event_id: int,
    now: Optional[datetime] = None,
) -> ResultShare:
    """Tell the patient, and record that they were told.

    Reuses `ResultShare` rather than inventing a second way to send something to
    a patient. The share still carries a `timeline_event_id`, because that is
    what the portal renders; the new `(result_type, result_id)` pair is what
    lets the *result* answer "was this communicated".
    """
    if review.status not in ("reviewed", "communicated"):
        raise ResultTransitionError("a result has to be reviewed before it is communicated")

    moment = now or _now()
    share = ResultShare(
        id=str(uuid4()),
        patient_id=review.patient_id,
        timeline_event_id=timeline_event_id,
        shared_by_user_id=actor.id,
        message=message,
        status="sent",
        shared_at=moment,
        result_type=review.result_type,
        result_id=review.result_id,
    )
    session.add(share)
    await session.flush()

    review.share_id = share.id
    review.status = "communicated"
    review.updated_at = moment
    return share


async def close_result(
    session: AsyncSession,
    review: ResultReview,
    *,
    actor: User,
    now: Optional[datetime] = None,
) -> ResultReview:
    """Close the loop.

    The guard here is the phase: a result whose decision was "tell the patient"
    stays open until they have been told. A clinic that cannot reach someone
    should see that on its list, because it is true.
    """
    if review.status == "closed":
        return review
    if review.status == "received":
        raise ResultTransitionError("an unreviewed result cannot be closed")
    if review.disposition == NEEDS_CONTACT and review.status != "communicated":
        raise ResultTransitionError(
            "this result was marked as needing patient contact; communicate it before closing"
        )

    moment = now or _now()
    review.status = "closed"
    review.closed_at = moment
    review.closed_by = actor.id
    review.updated_at = moment
    return review


async def reopen_result(
    session: AsyncSession,
    review: ResultReview,
    *,
    actor: User,
    window_days: int,
    now: Optional[datetime] = None,
) -> ResultReview:
    if review.status != "closed":
        raise ResultTransitionError("this result is not closed")
    moment = now or _now()
    if review.closed_at and moment - review.closed_at > timedelta(days=window_days):
        raise ResultTransitionError(f"the reopen window of {window_days} days has passed")

    review.status = "communicated" if review.share_id else "reviewed"
    review.closed_at = None
    review.closed_by = None
    review.updated_at = moment
    return review


async def list_reviews(
    session: AsyncSession,
    *,
    status: Optional[List[str]] = None,
    severity: Optional[str] = None,
    patient_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[ResultReview]:
    query = select(ResultReview)
    if status:
        query = query.where(ResultReview.status.in_(status))
    if severity:
        query = query.where(ResultReview.severity == severity)
    if patient_id:
        query = query.where(ResultReview.patient_id == patient_id)
    # Critical first, then oldest: the two things that decide what to open next.
    query = query.order_by(_severity_rank().asc(), ResultReview.created_at.asc())
    return list((await session.scalars(query.limit(min(limit, 200)).offset(offset))).all())


def _severity_rank():
    from sqlalchemy import case

    return case(
        (ResultReview.severity == "critical", 0),
        (ResultReview.severity == "abnormal", 1),
        (ResultReview.severity == "unclassified", 2),
        else_=3,
    )


async def load_result(session: AsyncSession, review: ResultReview) -> Optional[Any]:
    """The row the review is about, whichever table it is in."""
    if review.result_type == "lab":
        return await session.get(LabResult, int(review.result_id))
    return await session.get(ImagingStudy, review.result_id)


def result_out(result: Any, review: ResultReview) -> Dict[str, Any]:
    if review.result_type == "lab" and result is not None:
        return {
            "kind": "lab",
            "test_name": result.test_name,
            "value": result.value,
            "unit": result.unit,
            "reference_low": result.reference_low,
            "reference_high": result.reference_high,
            "taken_at": result.taken_at.isoformat(),
        }
    if result is not None:
        return {
            "kind": "imaging",
            "modality": result.modality,
            "body_part": result.body_part,
            "study_date": result.study_date.isoformat(),
            "finding_summary": result.finding_summary or "",
            "severity": result.severity,
        }
    # The review outlives a deleted result rather than disappearing with it:
    # "this was reviewed and the row is gone" is information.
    return {"kind": review.result_type, "missing": True}


__all__ = [
    "DISPOSITIONS",
    "NEEDS_CONTACT",
    "OPEN_STATUSES",
    "ResultTransitionError",
    "close_result",
    "communicate_result",
    "get_review",
    "list_reviews",
    "load_result",
    "record_imaging_study",
    "record_lab_result",
    "reopen_result",
    "result_out",
    "review_for_result",
    "review_result",
]
