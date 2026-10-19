"""What a patient may see of a lab result: only one a clinician communicated.

A lab result reaches the patient when a clinician reviews it and tells them
(`result_service.communicate_result`), which records a `ResultShare` pointing at
the result. This module turns those shares into the patient's view. Nothing
else is exposed: not a result that was reviewed but not communicated, not the
clinician's private note, not the decision, and not the classification as the
internal word it is stored as.

`standing` is the patient-safe form of the reviewed classification: it says
where the value sits against its range, and leaves the interpretation to the
clinician's own message.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import LabResult, ResultReview, ResultShare

#: The stored severity, as the patient is told about it.
_STANDING = {
    "critical": "needs_attention",
    "abnormal": "outside",
    "normal": "inside",
}


def _standing(severity: Optional[str]) -> str:
    return _STANDING.get(severity or "", "unknown")


def _direction(result: LabResult, standing: str) -> Optional[str]:
    if standing not in ("outside", "needs_attention"):
        return None
    if result.reference_low is not None and result.value < result.reference_low:
        return "below"
    if result.reference_high is not None and result.value > result.reference_high:
        return "above"
    return None


def lab_view(share: ResultShare, result: LabResult, review: Optional[ResultReview]) -> Dict[str, Any]:
    standing = _standing(review.severity if review else None)
    return {
        "share_id": share.id,
        "test_name": result.test_name,
        "value": result.value,
        "unit": result.unit,
        "taken_at": result.taken_at.isoformat(),
        "reference_low": result.reference_low,
        "reference_high": result.reference_high,
        "standing": standing,
        "direction": _direction(result, standing),
        "message": share.message,
        "shared_at": share.shared_at.isoformat(),
        "viewed_at": share.viewed_at.isoformat() if share.viewed_at else None,
    }


async def labs_for_shares(session: AsyncSession, shares: Iterable[ResultShare]) -> Dict[str, Dict[str, Any]]:
    """`share.id -> lab view` for the lab shares among `shares`. Two queries,
    however many shares there are. A share whose result no longer exists is
    skipped rather than shown half-empty."""
    lab_shares = [s for s in shares if s.result_type == "lab" and (s.result_id or "").isdigit()]
    if not lab_shares:
        return {}
    results = {
        r.id: r
        for r in (
            await session.scalars(
                select(LabResult).where(LabResult.id.in_([int(s.result_id) for s in lab_shares]))
            )
        ).all()
    }
    reviews = {
        r.share_id: r
        for r in (
            await session.scalars(
                select(ResultReview).where(ResultReview.share_id.in_([s.id for s in lab_shares]))
            )
        ).all()
    }
    views: Dict[str, Dict[str, Any]] = {}
    for share in lab_shares:
        result = results.get(int(share.result_id))
        if result is not None:
            views[share.id] = lab_view(share, result, reviews.get(share.id))
    return views


async def communicated_labs(session: AsyncSession, patient_id: str) -> List[Dict[str, Any]]:
    """The patient's communicated lab results, newest first."""
    shares = (
        await session.scalars(
            select(ResultShare)
            .where(
                ResultShare.patient_id == patient_id,
                ResultShare.status == "sent",
                ResultShare.result_type == "lab",
            )
            .order_by(ResultShare.shared_at.desc())
        )
    ).all()
    views = await labs_for_shares(session, shares)
    return [views[s.id] for s in shares if s.id in views]


__all__ = ["communicated_labs", "lab_view", "labs_for_shares"]
