"""Review queue for answers a clinician rated "not useful" (AB#16).

Clinician-only (mounted behind `_clinician_only`, see `main.py`). The queue is
shared: any clinician can pick up a rating, whoever gave it, and close it with
an outcome. Closing records who and when.

Listing returns provenance (provider, model, fallback) from the trace, not the
question or answer text; the consultation is opened by id or `trace_id` (for
example through the read-only review endpoint, which de-identifies it).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import get_current_user
from core.db import get_session
from data.schemas import Consultation, ResponseRating, User

from ..provenance import provenance

router = APIRouter()


class ReviewIn(BaseModel):
    outcome: Literal["model_failure", "source_failure", "false_alarm", "no_action"]
    note: str = Field("", max_length=500)


def queue_item(rating: ResponseRating, consultation: Consultation) -> dict[str, Any]:
    return {
        "rating_id": rating.id,
        "consultation_id": consultation.id,
        "trace_id": rating.trace_id or "",
        "created_at": rating.created_at.isoformat() if rating.created_at else None,
        "reason": rating.reason,
        "comment": rating.comment,
        "agents": list(consultation.agents or []),
        **provenance(consultation.trace),
        "review_status": rating.review_status,
        "review_outcome": rating.review_outcome,
        "review_note": rating.review_note,
        "reviewed_at": rating.reviewed_at.isoformat() if rating.reviewed_at else None,
    }


@router.get("/queue", summary="Answers rated not useful, oldest first")
async def queue(
    status: Literal["pending", "reviewed", "all"] = "pending",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = (
        select(ResponseRating, Consultation)
        .join(Consultation, Consultation.id == ResponseRating.consultation_id)
        .where(ResponseRating.value == "down")
        .order_by(ResponseRating.created_at.asc(), ResponseRating.id.asc())
    )
    if status != "all":
        stmt = stmt.where(ResponseRating.review_status == status)
    rows = (await session.execute(stmt.limit(limit + 1).offset(offset))).all()
    return {
        "items": [queue_item(r, c) for r, c in rows[:limit]],
        "limit": limit,
        "offset": offset,
        "has_more": len(rows) > limit,
    }


@router.post("/queue/{rating_id}/review", summary="Close a queue item with an outcome")
async def review(
    rating_id: str,
    body: ReviewIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rating = await session.scalar(
        select(ResponseRating).where(ResponseRating.id == rating_id, ResponseRating.value == "down")
    )
    if rating is None:
        raise HTTPException(status_code=404, detail="Not found")
    if rating.review_status == "reviewed":
        raise HTTPException(status_code=409, detail="Already reviewed")

    rating.review_status = "reviewed"
    rating.review_outcome = body.outcome
    rating.review_note = body.note.strip()
    rating.reviewed_by = user.id
    rating.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.commit()

    consultation = await session.get(Consultation, rating.consultation_id)
    assert consultation is not None  # FK
    return queue_item(rating, consultation)


__all__ = ["queue_item", "router"]
