"""Per-patient consultation memory — F-035's "memory" slice, scoped narrowly.

There is no multi-turn/session concept anywhere in this product today: each
`/consult` call is 100% stateless, `Consultation` has no `session_id`, and
the frontend never replays prior turns into a new request (confirmed by
direct inspection before writing this module). Building a generic
conversational-memory abstraction from scratch, with no validated product
need for multi-turn chat, would be exactly the premature complexity this
project's engineering discipline avoids.

What *does* already have a real hook and a real clinical use case: recalling
a patient's own recent consultations when answering a new question about
them. `patient_id` already links every `Consultation` to a patient — this
module just reads that.

Called from the API router, not the executor — the executor stays free of
any DB dependency, matching its existing design (`run_consultation`/
`stream_consultation` are pure functions of client/query/context).
"""

from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Consultation

_ANSWER_EXCERPT_CHARS = 200


async def recent_consultation_summaries(patient_id: str, session: AsyncSession, limit: int = 3) -> List[str]:
    """The `limit` most recent past consultations for `patient_id`, newest
    first, as short digests — or `[]` if there are none / `patient_id` is
    empty."""
    if not patient_id:
        return []
    rows = (
        await session.scalars(
            select(Consultation)
            .where(Consultation.patient_id == patient_id)
            .order_by(Consultation.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [f"Q: {row.query} → A: {row.answer[:_ANSWER_EXCERPT_CHARS]}" for row in rows]


__all__ = ["recent_consultation_summaries"]
