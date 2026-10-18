"""Review queue for answers that need a second look (AB#16, AB#17).

Two things put an answer in it: a clinician rated it "not useful"
(`ResponseRating`, `source="human"`), or the automatic grader scored it low
(`AutoGrade`, `source="auto"`). Both are closed the same way.

Clinician-only (mounted behind `_clinician_only`, see `main.py`). The queue is
shared: any clinician can pick up an item, whoever raised it, and close it
with an outcome. Closing records who and when.

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
from data.schemas import AutoGrade, Consultation, ResponseRating, User

from ..provenance import provenance

router = APIRouter()


class ReviewIn(BaseModel):
    outcome: Literal["model_failure", "source_failure", "false_alarm", "no_action"]
    note: str = Field("", max_length=500)


def queue_item(item: ResponseRating | AutoGrade, consultation: Consultation) -> dict[str, Any]:
    """One queue entry. `item_id` is the id to close it with."""
    base: dict[str, Any] = {
        "item_id": item.id,
        "consultation_id": consultation.id,
        "trace_id": item.trace_id or "",
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "agents": list(consultation.agents or []),
        **provenance(consultation.trace),
        "review_status": item.review_status,
        "review_outcome": item.review_outcome,
        "review_note": item.review_note,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }
    if isinstance(item, AutoGrade):
        return {
            **base,
            "source": "auto",
            "reason": None,
            "comment": "",
            "scores": item.scores,
            "overall": item.overall,
            "justification": item.justification,
            "grader": f"{item.grader_provider}/{item.grader_model}",
            "criteria_version": item.criteria_version,
        }
    return {**base, "source": "human", "reason": item.reason, "comment": item.comment}


def _human_stmt(status: str):
    stmt = (
        select(ResponseRating, Consultation)
        .join(Consultation, Consultation.id == ResponseRating.consultation_id)
        .where(ResponseRating.value == "down")
    )
    if status != "all":
        stmt = stmt.where(ResponseRating.review_status == status)
    return stmt.order_by(ResponseRating.created_at.asc(), ResponseRating.id.asc())


def _auto_stmt(status: str):
    stmt = (
        select(AutoGrade, Consultation)
        .join(Consultation, Consultation.id == AutoGrade.consultation_id)
        .where(AutoGrade.status == "graded", AutoGrade.review_status.is_not(None))
    )
    if status != "all":
        stmt = stmt.where(AutoGrade.review_status == status)
    return stmt.order_by(AutoGrade.created_at.asc(), AutoGrade.id.asc())


async def fetch_queue(
    session: AsyncSession, status: str, limit: int, offset: int
) -> tuple[list[tuple[ResponseRating | AutoGrade, Consultation]], bool]:
    """The page of queue entries (human and automatic merged, oldest first)
    and whether more follow. Each source is read up to the end of the page,
    then the two are merged: a page can never skip an item of either."""
    need = offset + limit + 1
    rows: list[tuple[ResponseRating | AutoGrade, Consultation]] = []
    for stmt in (_human_stmt(status), _auto_stmt(status)):
        rows += [(i, c) for i, c in (await session.execute(stmt.limit(need))).all()]
    rows.sort(key=lambda r: (r[0].created_at, r[0].id))
    page = rows[offset : offset + limit]
    return page, len(rows) > offset + limit


@router.get("/queue", summary="Answers rated not useful or graded low, oldest first")
async def queue(
    status: Literal["pending", "reviewed", "all"] = "pending",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    page, has_more = await fetch_queue(session, status, limit, offset)
    return {
        "items": [queue_item(i, c) for i, c in page],
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.post("/queue/{item_id}/review", summary="Close a queue item with an outcome")
async def review(
    item_id: str,
    body: ReviewIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    item: ResponseRating | AutoGrade | None = await session.scalar(
        select(ResponseRating).where(ResponseRating.id == item_id, ResponseRating.value == "down")
    )
    if item is None:
        item = await session.scalar(
            select(AutoGrade).where(
                AutoGrade.id == item_id, AutoGrade.status == "graded", AutoGrade.review_status.is_not(None)
            )
        )
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    if item.review_status == "reviewed":
        raise HTTPException(status_code=409, detail="Already reviewed")

    item.review_status = "reviewed"
    item.review_outcome = body.outcome
    item.review_note = body.note.strip()
    item.reviewed_by = user.id
    item.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.commit()

    consultation = await session.get(Consultation, item.consultation_id)
    assert consultation is not None  # FK
    return queue_item(item, consultation)


__all__ = ["fetch_queue", "queue_item", "router"]
